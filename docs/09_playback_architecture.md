# Playback Architecture Document
**Project**: Enterprise Video Management System (VMS)  
**Owner**: Playback Architect  

---

## 1. Timeline Compilation
- **Process**: Reads database segment start/end timestamps -> merges adjacent files within 5 seconds threshold -> outputs contiguous seek blocks and gaps.

## 2. Playback Concatenation Engine
- When multiple segments are requested, the backend dynamically builds an FFmpeg concat listing file.
- Launches FFmpeg with copy codecs:
  ```bash
  ffmpeg -f concat -safe 0 -i concat_list.txt -c copy -f mp4 -movflags frag_keyframe+empty_moov pipe:1
  ```
- Streams the result to the browser as a continuous clip supporting HTTP range seeking.
