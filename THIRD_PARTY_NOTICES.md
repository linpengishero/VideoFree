# Third-Party Components and Resources

**English** · [中文](THIRD_PARTY_NOTICES_ZH.md)

VideoFree is a media gateway that calls a user-configured ComfyUI installation,
installed nodes, models, and external services. Content listed below is not covered
by a single VideoFree license merely because it is referenced by this repository.

## ComfyUI and community nodes

ComfyUI and its community nodes are maintained by their respective authors. Their
copyrights and licenses remain with those rights holders. When installing or
redistributing a plugin, retain and follow the notices shipped by its upstream
project and release package.

## Models, LoRAs, fonts, and media

Models, LoRAs, fonts, sample files, and other media may carry separate use limits,
attribution requirements, or commercial restrictions. Review the source page and
the accompanying license before downloading, redistributing, or using an item in a
commercial project.

## OpenMontage

OpenMontage is located under `.agents/skills/openmontage/`. It can be used as an
independent skill and is not a runtime dependency of the VideoFree editor plugin.
Its AGPL-3.0 license applies independently. Keep the OpenMontage license, copyright,
source notices, and other required files with its source distribution.

## Other dependencies

Python, JavaScript packages, FFmpeg, and other dependencies retain the licenses of
their own projects. Listing a dependency does not transfer its copyright or grant a
VideoFree sublicense. The editor calls user-installed `ffmpeg` and `ffprobe` from
system `PATH`; this repository does not commit or distribute those binaries. See
`plugins/film-studio/INSTALL.md` for installation and verification instructions.
