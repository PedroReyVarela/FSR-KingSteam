"""Minimal pure-Python 7z reader (stdlib only) for machines without 7z/bsdtar.

Supports what the pinned OptiScaler archive and the AMD installer payload use: LZMA, LZMA2,
x86 BCJ and Copy coders in a simple chain, encoded headers, solid folders, an optional byte
offset where the archive starts (self-extracting EXE). Files are streamed, never held in RAM.
Anything else raises SevenZipError instead of guessing.
"""

import lzma
import os
import struct
import zlib
from pathlib import Path, PurePosixPath

CHUNK = 1024 * 1024


class SevenZipError(Exception):
    pass


class _Reader:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def byte(self):
        if self.pos >= len(self.data):
            raise SevenZipError("Truncated 7z header")
        value = self.data[self.pos]
        self.pos += 1
        return value

    def read(self, count):
        if count < 0 or self.pos + count > len(self.data):
            raise SevenZipError("Truncated 7z header")
        value = self.data[self.pos:self.pos + count]
        self.pos += count
        return value

    def number(self):
        first = self.byte()
        mask = 0x80
        value = 0
        for i in range(8):
            if not first & mask:
                high = first & (mask - 1)
                return value | (high << (8 * i))
            value |= self.byte() << (8 * i)
            mask >>= 1
        return value

    def bits(self, count):
        out = []
        current = 0
        mask = 0
        for _ in range(count):
            if mask == 0:
                current = self.byte()
                mask = 0x80
            out.append(bool(current & mask))
            mask >>= 1
        return out

    def defined_bits(self, count):
        if self.byte():  # all defined
            return [True] * count
        return self.bits(count)


def _filters_for(coders):
    """Turn 7z coders (in stored order) into a liblzma raw filter chain in decode order."""
    chain = []
    for method, props in coders:
        if method == b"\x21":  # LZMA2
            if len(props) != 1 or props[0] > 40:
                raise SevenZipError("Bad LZMA2 properties")
            dict_size = 0xFFFFFFFF if props[0] == 40 else (2 | (props[0] & 1)) << (props[0] // 2 + 11)
            chain.append({"id": lzma.FILTER_LZMA2, "dict_size": dict_size})
        elif method == b"\x03\x01\x01":  # LZMA
            if len(props) != 5:
                raise SevenZipError("Bad LZMA properties")
            lc_lp_pb = props[0]
            if lc_lp_pb >= 9 * 5 * 5:
                raise SevenZipError("Bad LZMA properties")
            chain.append({
                "id": lzma.FILTER_LZMA1,
                "lc": lc_lp_pb % 9, "lp": (lc_lp_pb // 9) % 5, "pb": lc_lp_pb // 45,
                "dict_size": struct.unpack("<I", props[1:5])[0],
            })
        elif method in (b"\x03\x03\x01\x03", b"\x04"):  # BCJ x86
            chain.append({"id": lzma.FILTER_X86})
        elif method == b"\x00":  # copy
            continue
        else:
            raise SevenZipError(f"Unsupported 7z method {method.hex()}")
    return chain


class _Folder:
    def __init__(self):
        self.coders = []          # [(method, props)] in stored order
        self.order = [0]          # coder indexes in decode order
        self.unpack_sizes = []    # per coder out stream
        self.pack_sizes = []
        self.crc = None
        self.pack_stream_index = 0
        self.substream_sizes = []
        self.substream_crcs = []

    def final_size(self):
        return self.unpack_sizes[self.order[-1]] if self.unpack_sizes else 0


def _parse_folder(reader):
    folder = _Folder()
    count = reader.number()
    if count == 0 or count > 8:
        raise SevenZipError("Unsupported 7z folder layout")
    total_in = total_out = 0
    for _ in range(count):
        flags = reader.byte()
        method = reader.read(flags & 0x0F)
        num_in = num_out = 1
        if flags & 0x10:
            num_in = reader.number()
            num_out = reader.number()
        props = reader.read(reader.number()) if flags & 0x20 else b""
        if flags & 0x80 or num_in != 1 or num_out != 1:
            raise SevenZipError("Unsupported 7z coder (multi-stream coders such as BCJ2)")
        folder.coders.append((method, props))
        total_in += num_in
        total_out += num_out
    bind_pairs = []
    for _ in range(total_out - 1):
        bind_pairs.append((reader.number(), reader.number()))
    if total_in - len(bind_pairs) != 1:
        raise SevenZipError("Unsupported 7z folder layout")
    # Work out the decode order: the coder fed by the packed stream runs first, and each bind pair
    # (in_index, out_index) feeds that coder's output into the coder owning in_index.
    bound_inputs = {in_index for in_index, _ in bind_pairs}
    first = [i for i in range(count) if i not in bound_inputs]
    if len(first) != 1:
        raise SevenZipError("Unsupported 7z coder graph")
    order = [first[0]]
    feeds = {out_index: in_index for in_index, out_index in bind_pairs}
    while len(order) < count:
        nxt = feeds.get(order[-1])
        if nxt is None or nxt in order:
            raise SevenZipError("Unsupported 7z coder graph")
        order.append(nxt)
    folder.order = order
    return folder


def _parse_streams_info(reader):
    pack_pos = 0
    pack_sizes = []
    folders = []
    while True:
        kind = reader.byte()
        if kind == 0x00:
            break
        if kind == 0x06:  # PackInfo
            pack_pos = reader.number()
            count = reader.number()
            while True:
                sub = reader.byte()
                if sub == 0x00:
                    break
                if sub == 0x09:
                    pack_sizes = [reader.number() for _ in range(count)]
                elif sub == 0x0A:
                    defined = reader.defined_bits(count)
                    for flag in defined:
                        if flag:
                            reader.read(4)
                else:
                    raise SevenZipError("Unexpected PackInfo property")
        elif kind == 0x07:  # UnPackInfo
            if reader.byte() != 0x0B:
                raise SevenZipError("Expected Folder")
            count = reader.number()
            if reader.byte() != 0:
                raise SevenZipError("External folders are unsupported")
            folders = [_parse_folder(reader) for _ in range(count)]
            if reader.byte() != 0x0C:
                raise SevenZipError("Expected CodersUnpackSize")
            for folder in folders:
                folder.unpack_sizes = [reader.number() for _ in folder.coders]
            while True:
                sub = reader.byte()
                if sub == 0x00:
                    break
                if sub == 0x0A:
                    defined = reader.defined_bits(count)
                    for folder, flag in zip(folders, defined):
                        if flag:
                            folder.crc = struct.unpack("<I", reader.read(4))[0]
                else:
                    raise SevenZipError("Unexpected UnPackInfo property")
        elif kind == 0x08:  # SubStreamsInfo
            counts = [1] * len(folders)
            sub = reader.byte()
            if sub == 0x0D:
                counts = [reader.number() for _ in folders]
                sub = reader.byte()
            for folder, n in zip(folders, counts):
                sizes = []
                if n:
                    if sub == 0x09:
                        sizes = [reader.number() for _ in range(n - 1)]
                    elif n > 1:
                        raise SevenZipError("Missing substream sizes")
                    sizes.append(folder.final_size() - sum(sizes))
                folder.substream_sizes = sizes
            if sub == 0x09:
                sub = reader.byte()
            for folder in folders:
                folder.substream_crcs = [None] * len(folder.substream_sizes)
                if len(folder.substream_sizes) == 1 and folder.crc is not None:
                    folder.substream_crcs = [folder.crc]
            while sub != 0x00:
                if sub == 0x0A:
                    need = [(f, i) for f in folders for i in range(len(f.substream_sizes))
                            if not (len(f.substream_sizes) == 1 and f.crc is not None)]
                    defined = reader.defined_bits(len(need))
                    for (folder, i), flag in zip(need, defined):
                        if flag:
                            folder.substream_crcs[i] = struct.unpack("<I", reader.read(4))[0]
                else:
                    raise SevenZipError("Unexpected SubStreamsInfo property")
                sub = reader.byte()
        else:
            raise SevenZipError(f"Unexpected StreamsInfo property {kind:#x}")
    # no SubStreamsInfo: each folder is one file
    for folder in folders:
        if not folder.substream_sizes:
            folder.substream_sizes = [folder.final_size()]
            folder.substream_crcs = [folder.crc]
    index = 0
    for folder in folders:
        folder.pack_stream_index = index
        folder.pack_sizes = pack_sizes[index:index + 1]
        index += 1
    return pack_pos, pack_sizes, folders


def _decode_folder(handle, base, folder, pack_offset):
    """Yield the decoded bytes of one folder."""
    size = folder.pack_sizes[0]
    chain = _filters_for([folder.coders[i] for i in reversed(folder.order)])
    handle.seek(base + pack_offset)
    remaining = size
    if not chain:
        while remaining:
            block = handle.read(min(CHUNK, remaining))
            if not block:
                raise SevenZipError("Truncated 7z data")
            remaining -= len(block)
            yield block
        return
    decoder = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=chain)
    produced = 0
    target = folder.final_size()
    while remaining and not decoder.eof:
        block = handle.read(min(CHUNK, remaining))
        if not block:
            raise SevenZipError("Truncated 7z data")
        remaining -= len(block)
        while True:
            out = decoder.decompress(block, max_length=CHUNK)
            block = b""
            if out:
                produced += len(out)
                yield out
            if decoder.eof or decoder.needs_input:
                break
    # output the decoder may still hold after the last input block
    while not decoder.eof and not decoder.needs_input:
        out = decoder.decompress(b"", max_length=CHUNK)
        if not out:
            break
        produced += len(out)
        yield out
    if produced != target:
        raise SevenZipError("Decoded size does not match the 7z header")


class Archive:
    def __init__(self, path, offset=0):
        self.path = Path(path)
        self.base = offset
        self.entries = []   # dict(name, size, folder, crc, empty, is_dir)
        self.folders = []
        self.pack_pos = 0
        self._load()

    def _load(self):
        with self.path.open("rb") as handle:
            handle.seek(self.base)
            head = handle.read(32)
            if len(head) != 32 or head[:6] != b"7z\xbc\xaf\x27\x1c":
                raise SevenZipError("Not a 7z archive")
            if zlib.crc32(head[12:32]) != struct.unpack("<I", head[8:12])[0]:
                raise SevenZipError("7z start header CRC mismatch")
            next_offset, next_size, next_crc = struct.unpack("<QQI", head[12:32])
            if next_size == 0:
                return
            handle.seek(self.base + 32 + next_offset)
            header = handle.read(next_size)
            if len(header) != next_size or zlib.crc32(header) != next_crc:
                raise SevenZipError("7z header CRC mismatch")
            reader = _Reader(header)
            kind = reader.byte()
            while kind == 0x17:  # EncodedHeader
                pack_pos, _, folders = _parse_streams_info(reader)
                if len(folders) != 1:
                    raise SevenZipError("Unsupported encoded header")
                decoded = b"".join(_decode_folder(handle, self.base, folders[0], 32 + pack_pos))
                if folders[0].crc is not None and zlib.crc32(decoded) != folders[0].crc:
                    raise SevenZipError("Encoded 7z header CRC mismatch")
                reader = _Reader(decoded)
                kind = reader.byte()
            if kind != 0x01:
                raise SevenZipError("Unexpected 7z header type")
            self._parse_header(reader)

    def _parse_header(self, reader):
        names = []
        empty_stream = empty_file = None
        while True:
            kind = reader.byte()
            if kind == 0x00:
                break
            if kind == 0x02:  # ArchiveProperties
                while reader.byte() != 0x00:
                    reader.read(reader.number())
            elif kind == 0x03:  # AdditionalStreamsInfo
                _parse_streams_info(reader)
            elif kind == 0x04:
                self.pack_pos, _, self.folders = _parse_streams_info(reader)
            elif kind == 0x05:
                count = reader.number()
                while True:
                    prop = reader.byte()
                    if prop == 0x00:
                        break
                    size = reader.number()
                    body = _Reader(reader.read(size))
                    if prop == 0x0E:
                        empty_stream = body.bits(count)
                    elif prop == 0x0F:
                        empty_file = body.bits(sum(empty_stream or []))
                    elif prop == 0x11:
                        if body.byte() != 0:
                            raise SevenZipError("External file names are unsupported")
                        raw = body.data[1:].decode("utf-16-le")
                        names = raw.split("\x00")[:count]
                if len(names) != count:
                    raise SevenZipError("File name count mismatch")
                self._build_entries(names, empty_stream or [False] * count, empty_file)
            else:
                raise SevenZipError(f"Unexpected header property {kind:#x}")

    def _build_entries(self, names, empty_stream, empty_file):
        stream_files = [(folder, i) for folder in self.folders for i in range(len(folder.substream_sizes))]
        stream_iter = iter(stream_files)
        empty_index = 0
        for position, name in enumerate(names):
            if empty_stream[position]:
                is_file = bool(empty_file[empty_index]) if empty_file and empty_index < len(empty_file) else False
                empty_index += 1
                self.entries.append({"name": name, "size": 0, "folder": None, "index": 0,
                                     "crc": None, "is_dir": not is_file})
            else:
                try:
                    folder, i = next(stream_iter)
                except StopIteration:
                    raise SevenZipError("More files than streams in 7z header")
                self.entries.append({"name": name, "size": folder.substream_sizes[i], "folder": folder,
                                     "index": i, "crc": folder.substream_crcs[i], "is_dir": False})

    def names(self):
        return [e["name"] for e in self.entries if not e["is_dir"]]

    def extract(self, destination_for):
        """Stream files out. destination_for(name) -> Path to write, or None to skip."""
        with self.path.open("rb") as handle:
            pack_offset = 32 + self.pack_pos
            by_folder = {}
            for entry in self.entries:
                if entry["folder"] is not None:
                    by_folder.setdefault(id(entry["folder"]), []).append(entry)
            for folder in self.folders:
                entries = sorted(by_folder.get(id(folder), []), key=lambda e: e["index"])
                wanted = [(e, destination_for(e["name"])) for e in entries]
                if any(dest for _, dest in wanted):
                    self._extract_folder(handle, folder, wanted, pack_offset)
                pack_offset += folder.pack_sizes[0]
        for entry in self.entries:
            if entry["folder"] is None:
                dest = destination_for(entry["name"])
                if dest is not None:
                    if entry["is_dir"]:
                        dest.mkdir(parents=True, exist_ok=True)
                    else:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(b"")

    def _extract_folder(self, handle, folder, wanted, pack_offset):
        stream = _decode_folder(handle, self.base, folder, pack_offset)
        pending = b""
        for entry, dest in wanted:
            out = None
            crc = 0
            if dest is not None:
                dest.parent.mkdir(parents=True, exist_ok=True)
                out = dest.open("wb")
            try:
                remaining = entry["size"]
                while remaining:
                    if not pending:
                        pending = next(stream, b"")
                        if not pending:
                            raise SevenZipError("Unexpected end of 7z data")
                    piece, pending = pending[:remaining], pending[remaining:]
                    remaining -= len(piece)
                    if out is not None:
                        out.write(piece)
                        crc = zlib.crc32(piece, crc)
            finally:
                if out is not None:
                    out.close()
            if dest is not None and entry["crc"] is not None and crc != entry["crc"]:
                dest.unlink(missing_ok=True)
                raise SevenZipError(f"CRC mismatch in {entry['name']}")


def safe_destination(root, name):
    relative = PurePosixPath(name.replace("\\", "/"))
    if relative.is_absolute() or not relative.parts or any(part in ("..", "") for part in relative.parts):
        raise SevenZipError(f"Refusing unsafe archive path: {name!r}")
    return Path(root).joinpath(*relative.parts)


def extract_all(archive_path, output_dir, offset=0):
    archive = Archive(archive_path, offset)
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    archive.extract(lambda name: safe_destination(root, name))


def extract_members(archive_path, members, offset=0):
    """members: {archive_member_name: destination Path}. Raises if one is missing."""
    archive = Archive(archive_path, offset)
    present = {e["name"].replace("\\", "/") for e in archive.entries}
    missing = [m for m in members if m not in present]
    if missing:
        raise SevenZipError("Member not found in archive: " + ", ".join(missing))
    archive.extract(lambda name: members.get(name.replace("\\", "/")))
