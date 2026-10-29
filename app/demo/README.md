# SwapPrint demo recorder
1. Start the app (`streamlit run app/streamlit_app.py --server.port 8601`), then run
   `.venv/bin/python app/demo/record_demo.py [storyboard.json] [--url=http://localhost:8601]`.
2. Output in `app/demo/out/`: `swapprint_demo.webm`, `swapprint_demo.mp4` (if ffmpeg is on PATH), `captions.srt`, `check_*.png`.
3. Edit `storyboard.json`: one step per caption, `{"say", "action", ...args, "hold"}`; steps run top to bottom.
4. Actions: `goto_tab {tab}`, `click_button {name}`, `select_sidebar {label, option}`, `radio_sidebar {label, option}`,
   `click_image {x, y}` (0..1 fractions), `scroll_to_text {text}`, `wait`. `"check": "name"` saves a frame as `out/check_name.png`.
5. `hold` is the number of seconds to stay on screen after the app goes idle. Make it longer for longer captions.
6. Do not commit `out/`: the videos are large.
