# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A single-file Python application, `CCTV_COUNT_v10_INIT_GERAK.py`, that counts cars and motorcycles crossing user-drawn zones in a CCTV stream for Bapenda. It uses YOLOv8 (Ultralytics) with ByteTrack. Code, comments, console output and generated files are written in **Indonesian**, so keep new code and messages in that style.

The module docstring at the top of the file is the user manual. It covers counting rules, keyboard controls, accepted URL formats and output files. Update it when behavior changes. It still refers to the script as `traffic_counter_v5.py`; the real filename is `CCTV_COUNT_v10_INIT_GERAK.py`.

## Running

There is no build system, requirements file, test suite or linter config. Dependencies are `opencv-python`, `numpy`, `requests` and `ultralytics`. `XlsxWriter` is optional, and `ensure_excel_dependency()` pip-installs it at startup if it is missing.

```
python CCTV_COUNT_v10_INIT_GERAK.py                 # prompts for stream URL, then metadata (NOP, CCTV_ID, NAMA_OP, ALAMAT_OP), then ROI drawing
python CCTV_COUNT_v10_INIT_GERAK.py "<url|uuid>"    # use the given stream source
python CCTV_COUNT_v10_INIT_GERAK.py --report [id]   # regenerate today's HTML report(s) from the CSV log without opening a camera
```

A run is interactive: it needs a GUI (`cv2.imshow`), stdin input, and a live stream. On the first run, `yolov8l.pt` is downloaded automatically. To check that the file still parses without running it, use `python -m py_compile CCTV_COUNT_v10_INIT_GERAK.py`.

## Architecture

**Process and thread layout.** Each stage runs separately so the OpenCV window never shows "Not Responding":
- `stream_worker` runs in its own process. It opens the stream (Jasnita API token, RTSP, RTMP or HTTP), refreshes the Jasnita token every `TOKEN_REFRESH_SEC`, retries with backoff, and logs connect and disconnect events to `log_koneksi_stream.csv`.
- `inference_worker` runs in its own process. It runs YOLO `model.track()` with ByteTrack, using a config written to `bytetrack_traffic.yaml` from `TRACKER_CFG`, and sends back only plain numpy arrays.
- `run()` is the main process and GUI loop. It handles per-track state, counting decisions, drawing and keyboard input.
- `writer_worker` is a thread that does all disk I/O: capture JPGs, CSV logs, the Excel workbook and the HTML report. The GUI loop sends tuples (`"log_event"`, `"summary"`, `"report"`) to it through `write_queue`, and `None` stops it. Never do disk I/O directly in the GUI loop.
- The inter-process queues are `maxsize=1` and use `_push_latest`, so stale frames are dropped rather than queued.

**Counting logic (geometry + `TrackState`).** The user draws three polygons: yellow for initialization, green for the motorcycle counting line, and red for the car, bus and truck counting line. A track is counted only if all of these hold:
1. It touched yellow first. `maybe_init_by_motion` also allows initialization when the body touches yellow and the vehicle moves forward.
2. It moves in the yellow→green or yellow→red direction. Reverse movement is flagged and never counted.
3. It is moving, not parked (`update_motion_state`, `PARK_*` / `MOVE_*`).
4. Class voting has confirmed its class (`MIN_CLASS_*`, `CLASS_SCORE_MARGIN`).
5. It meets the travel and approach thresholds for `COUNT_CONFIRM_FRAMES` consecutive frames.

The camera feeds have low FPS, so a vehicle can go past a counting line between two detections. For that reason, a touch on the green or red line is latched in `TrackState.cross` by `update_cross_latch`, which must run before `should_count`. The confirming observation then only has to show that the vehicle hasn't moved back from the latch point; it doesn't need to still be touching the line. Detection timing uses the frame timestamp taken in `inference_worker`, not the time the GUI receives the result.

The operator can left-click a vehicle to put a red X on it (`toggle_exclusion`). Excluded tracks (`TrackState.excluded`) are never counted, and every count gate checks this flag. The marks are kept in `excl_marks` inside `run()`. A mark follows the vehicle when the tracker changes its ID, either by relink or by bbox overlap; overlap matching is used only for brand-new IDs. Marks on parked vehicles are kept for `EXCLUDE_KEEP_PARKED_SEC`.

`should_count` is the main gate, and `why_not` / `diag_miss` explain rejections. That explanation appears as on-screen debug labels (key `d`) and as `[DIAG]` console lines. Supporting mechanisms:
- `find_relink` reconnects a track to its new ID when ByteTrack switches IDs.
- `is_duplicate_count` stops the same vehicle from being counted twice.
- `missed_crossing_group` (`MISSED_FLUSH`) counts tracks that clearly crossed but missed the per-frame gate, at the point the track ends.

Counters reset at midnight.

**Tuning.** Behavior is controlled by the module-level constants in section "0. KONFIGURASI" at the top of the file. Each one has an inline comment giving its rationale. Prefer changing those constants over hardcoding values in the logic.

**Outputs** go next to the script (`BASE_DIR`):
- `log_kendaraan_terhitung.csv`: the main event log, using the Bapenda field schema enforced by `ensure_event_log_schema`.
- `_capture_index.csv`
- `log_capture_kendaraan.xlsx`: rewritten periodically with embedded images. If the file is locked, for example because it is open in Excel, the write is deferred and retried.
- `ringkasan_hitungan.csv`
- `capture/<CCTV_ID>/<class>/<date>/*.jpg`
- `laporan/laporan_<CCTV_ID>_<date>.html`: a self-contained report with an SVG hourly chart.

## Notes

- Jasnita credentials are hardcoded at the top of the file as `JASNITA_USER` / `JASNITA_PASS`. Only `JASNITA_URL` reads from the environment.
- Keep `mp.freeze_support()` and the `if __name__ == "__main__"` guard. Windows multiprocessing uses spawn, so worker functions must stay at module top level and be picklable.
- `OPENCV_FFMPEG_CAPTURE_OPTIONS` is set before `import cv2` on purpose. Do not reorder these imports.
