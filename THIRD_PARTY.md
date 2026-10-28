# Third-party material

FSR-KingSteam's own code (everything outside the items below) is MIT-licensed, see `LICENSE`.

## Decky plugin template (build scaffolding)

`rollup.config.js`, `tsconfig.json`, `decky.pyi`, `plugin.json` and the shape of `package.json` come from the
Decky plugin template.

BSD 3-Clause License. Copyright (c) 2022-2024, Steam Deck Homebrew. All rights reserved.
Redistribution and use in source and binary forms, with or without modification, are permitted
provided that the conditions of the BSD 3-Clause license are met: source redistributions keep this
notice and disclaimer, binary redistributions reproduce them in the documentation, and the names of
the copyright holder and contributors are not used to endorse derived products. THIS SOFTWARE IS
PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND; see https://opensource.org/license/bsd-3-clause for
the full text.

## Binaries the plugin installs (not modified)

- OptiScaler and OptiPatcher, by the OptiScaler team. Pinned release archives are bundled in the
  plugin ZIP; their URLs and SHA-256 are in `data/runtime-assets.json`. The OptiScaler archive in turn
  contains third-party libraries (Nukem9's dlssg-to-fsr3, Intel XeSS, AMD FidelityFX); their license
  texts are in `licenses/`.
- AMD FSR 4 driver DLLs (`amdxcffx64.dll`, `amdvkffx64.dll`): NOT redistributed. The plugin downloads
  AMD's driver package on the user's device, extracts these two files and checks their SHA-256.
- Community FSR4 DLLs in `community/` are redistributed as provided by their authors; each folder has
  an `info.json` describing it.
