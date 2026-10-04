# SUN RGB-D reference data (local only)

This folder holds the real-photo reference set used by `tests/realdata`. Its contents are
**not** in git: the data is licensed for research use only and this repository is public.
Only this README is tracked; the list of frames used is `tests/realdata/nyu_subset.json`.

Fetch it. Annotations come from SUN RGB-D (14.5 MB, read out of the toolbox zip with a few
paced range requests); photos and scene types come from NYU's own labelled set (one resumable
3 GB download), cropped exactly as SUN RGB-D crops the NYU frames:

```bash
uv sync --extra realdata
uv run python -m tests.realdata.fetch --accept-license
```

What lands here:

```
deps/sunrgbd/LICENSE_ACCEPTED          when and by whom the terms were accepted
deps/sunrgbd/Metadata/SUNRGBDMeta.mat  camera, gravity, room layout, 3-D/2-D boxes for 10,335 frames
deps/sunrgbd/nyu_depth_v2_labeled.mat  NYU Depth v2 labelled set (1,449 frames; photos, depth, labels, scene types)
deps/sunrgbd/nyu/NYU0001/image.jpg     the photo (561 x 427 crop of the NYU Depth v2 frame)
deps/sunrgbd/nyu/NYU0001/scene.txt     scene type
deps/sunrgbd/nyu/NYU0001/truth.json    ground truth converted to this project's conventions
```

Source: https://rgbd.cs.princeton.edu/ — research use only. If you publish anything that
uses it, cite:

- S. Song, S. Lichtenberg, J. Xiao. *SUN RGB-D: A RGB-D Scene Understanding Benchmark Suite.* CVPR 2015.
- N. Silberman, D. Hoiem, P. Kohli, R. Fergus. *Indoor Segmentation and Support Inference from RGBD Images.* ECCV 2012.
