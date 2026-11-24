# Changelog

All notable changes to this project are documented here. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.1.0] - 2026-11-23

Exports now default to a `drum-loops/` folder next to the repo, alongside `../patterns` and `../sf2`, so the whole setup lives in one parent folder. If you relied on the old `~/Music/drum-loops` default, set `DRUM_EXPORT_DIR=~/Music/drum-loops`.

### Changed
- The default export folder is `../drum-loops`, next to the repo like `../patterns` and `../sf2`, instead of `~/Music/drum-loops` (#18)

## [1.0.0] - 2026-11-23

First public release of the drum loop toolkit: groom, which turns a MIDI drum loop library into a checked, tagged catalogue, and a SvelteKit dashboard for browsing, previewing, curating and sequencing it. You can try it without a library using the synthetic test catalogue. Exports default to `~/Music/drum-loops`. MIT licensed.

### Added
- README: dashboard screenshot, "Try it without a loop library" (the synthetic fixture catalogue), SoundFont workaround (#14), current status, related projects, license scope (#15)
- MIT license (#12)

### Fixed
- The default export folder is `~/Music/drum-loops` instead of a hard-coded personal path; `DRUM_EXPORT_DIR` still overrides it (#10)

### Changed
- `.gitignore`: Windows thumbnails and Sublime workspaces (#8)

[Unreleased]: https://github.com/lucidbeaming/drum-loop-browser/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/lucidbeaming/drum-loop-browser/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/lucidbeaming/drum-loop-browser/releases/tag/v1.0.0
