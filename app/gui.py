"""Giao dien: chon CHE DO, bat/tat tung chieu, va chinh cac can gat do tre.

Hai che do:
  - "Xem video / nghe 1 chieu": chi chieu Anh -> Viet. Dung cho xem video,
    xem hop ma khong can noi.
  - "Hop 2 chieu": them chieu Viet -> Anh de doi tac nghe duoc ban.

Dung polling dinh ky (root.after) de doc queue tu pipeline - KHONG update GUI
truc tiep tu thread khac (Tkinter khong thread-safe).

Chay: python main.py
"""
import queue
import threading
import tkinter as tk
from tkinter import ttk

from app.audio_devices import (
    get_default_input_device,
    get_default_loopback_device,
    get_default_output_device,
    is_same_physical_device,
    list_input_devices,
    list_loopback_devices,
    list_output_devices,
    suggest_output_device,
)
from app.config import LISTEN_DIRECTIONS, default_config
from app.models import ModelHub
from app.pipeline import DirectionPipeline

POLL_MS = 150

MODEL_CHOICES_GPU = [
    ("medium - chinh xac nhat (~0.4s)", "medium"),
    ("small  - nhanh hon (~0.2s)", "small"),
    ("base   - nhanh nhat", "base"),
    ("large-v3 - tot nhat (can VRAM lon)", "large-v3"),
]

MODEL_CHOICES_CPU = [
    ("base  - nhanh nhat (~0.5s/cau)", "base"),
    ("small - can bang (~1.7s/cau)", "small"),
    ("medium - chinh xac nhat (rat cham)", "medium"),
]


class DirectionPanel(ttk.LabelFrame):
    """Mot khung dieu khien + hien thi cho 1 chieu dich."""

    def __init__(self, parent, app: "App", direction, source_kind: str):
        super().__init__(parent, text=direction.label, padding=6)
        self.app = app
        self.direction = direction
        self.source_kind = source_kind  # "loopback" | "mic"
        self.pipeline: DirectionPipeline | None = None

        row = ttk.Frame(self)
        row.pack(fill=tk.X)

        src_label = "Nguon (am thanh may):" if source_kind == "loopback" else "Nguon (mic cua ban):"
        ttk.Label(row, text=src_label).grid(row=0, column=0, sticky="w")
        self.source_combo = ttk.Combobox(row, state="readonly", width=34)
        self.source_combo.grid(row=0, column=1, padx=4)
        self.source_combo.bind("<<ComboboxSelected>>", lambda _e: self.app.check_warnings())

        if source_kind == "loopback":
            self.detect_btn = ttk.Button(row, text="Tu do", width=7, command=self._on_detect)
            self.detect_btn.grid(row=0, column=2, padx=(0, 8))

        out_label = "Phat ra:" if source_kind == "loopback" else "Phat vao (mic ao):"
        ttk.Label(row, text=out_label).grid(row=0, column=3, sticky="w")
        self.output_combo = ttk.Combobox(row, state="readonly", width=34)
        self.output_combo.grid(row=0, column=4, padx=4)
        self.output_combo.bind("<<ComboboxSelected>>", lambda _e: self.app.check_warnings())

        if source_kind == "loopback":
            # Ngon ngu NGUON phai khop voi thu tieng thuc su dang phat ra.
            # Chon sai (vd. nguon tieng Viet ma de "nghe tieng Anh") thi Whisper
            # bi ep phien am sai ngon ngu -> ra rac -> bo loc loai sach -> IM LANG.
            lang_row = ttk.Frame(self)
            lang_row.pack(fill=tk.X, pady=(4, 0))
            ttk.Label(lang_row, text="Ngon ngu dang nghe:").pack(side=tk.LEFT)
            self.lang_combo = ttk.Combobox(
                lang_row, state="readonly", width=34,
                values=[lbl for lbl, _ in LISTEN_DIRECTIONS.values()],
            )
            self.lang_combo.current(0)
            self.lang_combo.pack(side=tk.LEFT, padx=6)
            self.lang_combo.bind("<<ComboboxSelected>>", self._on_lang_change)
            ttk.Label(
                lang_row,
                text="<- chon dung thu tieng dang phat, sai thi khong ra ket qua nao",
                foreground="#888",
            ).pack(side=tk.LEFT, padx=6)

        ctrl = ttk.Frame(self)
        ctrl.pack(fill=tk.X, pady=(4, 2))
        self.toggle_btn = ttk.Button(ctrl, text="Bat", width=10, command=self._on_toggle)
        self.toggle_btn.pack(side=tk.LEFT)
        self.pause_btn = ttk.Button(ctrl, text="Tam dung", command=self._on_pause, state="disabled")
        self.pause_btn.pack(side=tk.LEFT, padx=6)

        self.speak_var = tk.BooleanVar(value=direction.speak)
        ttk.Checkbutton(
            ctrl, text="Doc thanh tieng", variable=self.speak_var, command=self._on_speak_toggle
        ).pack(side=tk.LEFT, padx=6)

        self.lag_var = tk.StringVar(value="")
        ttk.Label(ctrl, textvariable=self.lag_var, foreground="#888").pack(side=tk.LEFT, padx=10)

        self.status_var = tk.StringVar(value="Chua bat.")
        ttk.Label(ctrl, textvariable=self.status_var, foreground="#0a6").pack(side=tk.RIGHT)

        texts = ttk.Frame(self)
        texts.pack(fill=tk.BOTH, expand=True)
        texts.columnconfigure(0, weight=1)
        texts.columnconfigure(1, weight=1)
        texts.rowconfigure(1, weight=1)

        src_title = "Tieng Anh nghe duoc" if direction.key == "en2vi" else "Tieng Viet ban noi"
        dst_title = "Ban dich tieng Viet" if direction.key == "en2vi" else "Ban dich tieng Anh"
        self.src_title_label = ttk.Label(texts, text=src_title)
        self.src_title_label.grid(row=0, column=0, sticky="w")
        self.dst_title_label = ttk.Label(texts, text=dst_title)
        self.dst_title_label.grid(row=0, column=1, sticky="w")

        self.src_text = tk.Text(texts, wrap="word", height=7)
        self.src_text.grid(row=1, column=0, sticky="nsew", padx=(0, 4))
        self.dst_text = tk.Text(texts, wrap="word", height=7)
        self.dst_text.grid(row=1, column=1, sticky="nsew", padx=(4, 0))

        # Nhan nguoi noi hien mau xanh dam cho de phan biet voi noi dung
        for widget in (self.src_text, self.dst_text):
            widget.tag_configure("spk", foreground="#06c", font=("TkDefaultFont", 9, "bold"))

    # ---- thiet bi ----

    def refresh_devices(self, loopbacks, inputs, outputs) -> None:
        if self.source_kind == "loopback":
            self.source_map = {f"[{d.index}] {d.name}": d for d in loopbacks}
        else:
            self.source_map = {f"[{d.index}] {d.name}": d for d in inputs}
        self.output_map = {f"[{d.index}] {d.name}": d for d in outputs}

        self.source_combo["values"] = list(self.source_map.keys())
        self.output_combo["values"] = list(self.output_map.keys())

        try:
            default_src = (
                get_default_loopback_device() if self.source_kind == "loopback"
                else get_default_input_device()
            )
            key = f"[{default_src.index}] {default_src.name}"
            if key in self.source_map:
                self.source_combo.set(key)
            elif self.source_map:
                self.source_combo.current(0)
        except Exception:
            if self.source_map:
                self.source_combo.current(0)

        try:
            if self.source_kind == "loopback":
                src = self.source_map.get(self.source_combo.get())
                suggested = suggest_output_device(src) if src else None
                key = f"[{suggested.index}] {suggested.name}" if suggested else None
                if key and key in self.output_map:
                    self.output_combo.set(key)
                elif self.output_map:
                    self.output_combo.current(0)
            else:
                # Chieu Viet->Anh: phai phat vao thiet bi ma MIC AO nghe duoc.
                # Stereo Mix (Realtek) chi nghe duoc tieng phat ra card Realtek,
                # nen khong the chon bua thiet bi phat dau tien.
                self._select_output_for_virtual_mic()
        except Exception:
            if self.output_map:
                self.output_combo.current(0)

    def _select_output_for_virtual_mic(self) -> None:
        """Chon output sao cho mic ao cua Zoom nghe duoc (ghep dung card)."""
        from app.audio_devices import suggest_output_for_virtual_mic
        from app.route_check import find_virtual_mics

        try:
            mics = find_virtual_mics()
            if mics:
                out = suggest_output_for_virtual_mic(mics[0])
                if out is not None:
                    key = f"[{out.index}] {out.name}"
                    if key in self.output_map:
                        self.output_combo.set(key)
                        self.status_var.set(f"Zoom nen dat mic = {mics[0].name[:28]}")
                        return
        except Exception:
            pass
        if self.output_map:
            self.output_combo.current(0)

    def _on_detect(self) -> None:
        """Tu do thiet bi nao DANG co am thanh phat ra."""
        self.detect_btn.config(state="disabled")
        self.status_var.set("Dang do am thanh (3s)...")

        def _work():
            from app.levels import find_active_loopback
            found = find_active_loopback(probe_s=3.0)
            self.app.ui_queue.put(lambda: self._detect_done(found))

        threading.Thread(target=_work, daemon=True).start()

    def _detect_done(self, found) -> None:
        self.detect_btn.config(state="normal")
        if found is None:
            self.status_var.set("Khong thay thiet bi nao co tieng.")
            return
        key = f"[{found.index}] {found.name}"
        if key in self.source_map:
            self.source_combo.set(key)
            self.status_var.set(f"Tim thay: {found.name[:30]}")
            self.app.check_warnings()
        else:
            self.status_var.set("Tim thay nhung khong co trong danh sach - bam 'Lam moi'.")

    def selected_source(self):
        return self.source_map.get(self.source_combo.get())

    def selected_output(self):
        return self.output_map.get(self.output_combo.get())

    # ---- dieu khien ----

    def _on_toggle(self) -> None:
        if self.pipeline is not None and self.pipeline.is_running():
            self.pipeline.stop()
            self.pipeline = None
            self.toggle_btn.config(text="Bat")
            self.pause_btn.config(state="disabled")
            self.status_var.set("Da dung.")
            self.lag_var.set("")
            return

        source, output = self.selected_source(), self.selected_output()
        if source is None or output is None:
            self.status_var.set("Chua chon du thiet bi.")
            return

        self.direction.speak = self.speak_var.get()
        self.pipeline = DirectionPipeline(
            self.direction, self.app.cfg.audio, self.app.hub, source, output,
            result_queue=self.app.result_queue, status_queue=self.app.status_queue,
        )
        self.app.apply_latency_settings(self.pipeline)

        self.toggle_btn.config(state="disabled")
        self.status_var.set("Dang tai model...")

        def _load_and_start():
            try:
                self.pipeline.load_models()
                self.pipeline.start()
            except Exception as exc:
                self.app.error_queue.put((self.direction.key, str(exc)))
            finally:
                self.app.ui_queue.put(self._after_start)

        threading.Thread(target=_load_and_start, daemon=True).start()

    def _after_start(self) -> None:
        self.toggle_btn.config(state="normal")
        if self.pipeline is not None and self.pipeline.is_running():
            self.toggle_btn.config(text="Tat")
            self.pause_btn.config(state="normal")

    def _on_lang_change(self, _evt=None) -> None:
        """Doi cap ngon ngu cho khung nghe. Phai TAT roi BAT lai de ap dung."""
        keys = list(LISTEN_DIRECTIONS.keys())
        idx = self.lang_combo.current()
        _label, factory = LISTEN_DIRECTIONS[keys[idx]]

        new_dir = factory()
        new_dir.speak = self.speak_var.get()
        self.direction = new_dir
        self.config(text=new_dir.label)

        # Doi tieu de 2 khung van ban cho khop ngon ngu moi
        if new_dir.stt_language == "auto":
            src_title = "Nguyen van (Anh hoac Viet)"
        else:
            src_title = "Tieng Anh nghe duoc" if new_dir.stt_language == "en" else "Tieng Viet nghe duoc"
        dst_title = "Ban dich tieng Viet" if new_dir.tgt_language == "vi" else "Ban dich tieng Anh"
        self.src_title_label.config(text=src_title)
        self.dst_title_label.config(text=dst_title)

        if self.pipeline is not None and self.pipeline.is_running():
            self.status_var.set("Da doi ngon ngu - TAT roi BAT lai de ap dung.")
        else:
            self.status_var.set(f"Se nghe tieng {'Anh' if new_dir.stt_language == 'en' else 'Viet'}.")

    def _on_speak_toggle(self) -> None:
        self.direction.speak = self.speak_var.get()
        if self.pipeline is not None:
            if self.speak_var.get():
                self.pipeline.speak.set()
            else:
                self.pipeline.speak.clear()
        self.app.check_warnings()

    def _on_pause(self) -> None:
        if self.pipeline is None:
            return
        if self.pipeline.is_paused():
            self.pipeline.resume()
            self.pause_btn.config(text="Tam dung")
        else:
            self.pipeline.pause()
            self.pause_btn.config(text="Tiep tuc")

    def append(self, result) -> None:
        prefix = result.speaker_label or ""
        # Che do tu nhan dien: cho biet cau nay Whisper nghe ra tieng gi
        if result.detected_lang and self.direction.stt_language == "auto":
            tag = "EN" if result.detected_lang == "en" else "VI"
            prefix = f"{prefix} [{tag}]" if prefix else f"[{tag}]"
        if prefix:
            prefix += ": "

        # Cau von da dung ngon ngu dich thi khong co ban dich - noi ro thay vi de trong
        translated = result.translated_text or "(da dung ngon ngu dich, khong can dich)"

        for widget, text in ((self.src_text, result.source_text),
                             (self.dst_text, translated)):
            if prefix:
                widget.insert(tk.END, prefix, "spk")
            widget.insert(tk.END, text + "\n")
            widget.see(tk.END)

        note = f"Tre {result.lag_s:.1f}s"
        if result.dropped:
            note += f" (bo {result.dropped} cau)"
        self.lag_var.set(note)

    def stop(self) -> None:
        if self.pipeline is not None:
            self.pipeline.stop()
            self.pipeline = None


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Phien Dich Cuoc Hop - Anh <-> Viet (offline)")
        self.geometry("1040x820")

        self.cfg = default_config()          # da tu do phan cung ben trong
        from app.hardware import detect
        self.hw = detect()

        self.status_queue: queue.Queue = queue.Queue()
        self.result_queue: queue.Queue = queue.Queue()
        self.error_queue: queue.Queue = queue.Queue()
        self.ui_queue: queue.Queue = queue.Queue()
        self.hub = ModelHub(self.cfg, status_cb=lambda m: self.status_queue.put(m))

        self._build_mode_bar()
        self._build_settings()

        self.warn_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.warn_var, foreground="#c40",
                  padding=(8, 0), wraplength=1010).pack(fill=tk.X)

        body = ttk.Frame(self, padding=8)
        body.pack(fill=tk.BOTH, expand=True)
        self.body = body

        self.panel_en2vi = DirectionPanel(body, self, self.cfg.en2vi, "loopback")
        self.panel_vi2en = DirectionPanel(body, self, self.cfg.vi2en, "mic")
        self.panels = {"en2vi": self.panel_en2vi, "vi2en": self.panel_vi2en}

        self.refresh_devices()
        self._apply_mode()
        self.after(POLL_MS, self._poll)

    # ---- thanh chon che do ----

    def _build_mode_bar(self) -> None:
        bar = ttk.LabelFrame(self, text="Che do", padding=6)
        bar.pack(fill=tk.X, padx=8, pady=(8, 4))

        self.mode_var = tk.StringVar(value="watch")
        ttk.Radiobutton(
            bar, text="Xem video / nghe 1 chieu  (Anh -> Viet)",
            variable=self.mode_var, value="watch", command=self._apply_mode,
        ).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Radiobutton(
            bar, text="Hop 2 chieu  (them Viet -> Anh cho doi tac nghe)",
            variable=self.mode_var, value="meeting", command=self._apply_mode,
        ).pack(side=tk.LEFT)

        ttk.Button(bar, text="Lam moi thiet bi", command=self.refresh_devices).pack(side=tk.RIGHT)
        self.global_status = tk.StringVar(value="San sang.")
        ttk.Label(bar, textvariable=self.global_status).pack(side=tk.RIGHT, padx=10)

    def _apply_mode(self) -> None:
        self.panel_en2vi.pack_forget()
        self.panel_vi2en.pack_forget()

        self.panel_en2vi.pack(fill=tk.BOTH, expand=True, pady=(0, 6))
        if self.mode_var.get() == "meeting":
            self.panel_vi2en.pack(fill=tk.BOTH, expand=True)
        else:
            self.panel_vi2en.stop()
            self.panel_vi2en.toggle_btn.config(text="Bat")
            self.panel_vi2en.pause_btn.config(state="disabled")
        self.check_warnings()

    # ---- thanh cai dat do tre ----

    def _build_settings(self) -> None:
        box = ttk.LabelFrame(self, text="Toc do / do tre", padding=6)
        box.pack(fill=tk.X, padx=8, pady=(0, 4))

        ttk.Label(box, text="Model nhan dang:").grid(row=0, column=0, sticky="w")
        # Danh sach va mac dinh phu thuoc phan cung da do duoc
        self.model_choices = MODEL_CHOICES_GPU if self.hw.has_cuda else MODEL_CHOICES_CPU
        self.model_combo = ttk.Combobox(
            box, state="readonly", width=30, values=[c[0] for c in self.model_choices]
        )
        preset = [c[1] for c in self.model_choices]
        self.model_combo.current(preset.index(self.cfg.stt.model_size)
                                 if self.cfg.stt.model_size in preset else 0)
        self.model_combo.grid(row=0, column=1, padx=4)
        self.model_combo.bind("<<ComboboxSelected>>", self._on_model_change)

        ttk.Label(box, text="Toc do doc:").grid(row=0, column=2, sticky="w", padx=(16, 0))
        self.speed_var = tk.DoubleVar(value=0.9)
        ttk.Scale(box, from_=0.7, to=1.3, variable=self.speed_var,
                  command=self._on_speed_change, length=120).grid(row=0, column=3, padx=4)
        self.speed_label = tk.StringVar(value="0.90x")
        ttk.Label(box, textvariable=self.speed_label, width=6).grid(row=0, column=4)

        self.drop_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(box, text="Bo cau cu khi bi tre", variable=self.drop_var,
                        command=self._on_drop_change).grid(row=0, column=5, padx=(16, 4))

        ttk.Label(box, text="Tre toi da (giay):").grid(row=0, column=6, sticky="w")
        self.maxlag_var = tk.IntVar(value=6)
        ttk.Spinbox(box, from_=2, to=30, textvariable=self.maxlag_var, width=4,
                    command=self._on_drop_change).grid(row=0, column=7, padx=4)

        self.hint_var = tk.StringVar(
            value=f"Phan cung: {self.hw.summary()}   |   "
                  "Doc thanh tieng mat ~6s cho 1 cau dai -> muon nhanh nhat thi bo tich 'Doc thanh tieng'."
        )
        ttk.Label(box, textvariable=self.hint_var, foreground="#666").grid(
            row=1, column=0, columnspan=8, sticky="w", pady=(4, 0)
        )

    def _on_model_change(self, _evt=None) -> None:
        idx = self.model_combo.current()
        new_size = self.model_choices[idx][1]
        if new_size == self.cfg.stt.model_size:
            return
        self.cfg.stt.model_size = new_size
        # Phai tao ModelHub moi de load lai Whisper
        self.hub = ModelHub(self.cfg, status_cb=lambda m: self.status_queue.put(m))
        running = [p for p in self.panels.values() if p.pipeline is not None]
        if running:
            self.global_status.set(f"Da doi model sang '{new_size}' - TAT roi BAT lai de ap dung.")
        else:
            self.global_status.set(f"Model nhan dang: {new_size}")

    def _on_speed_change(self, _val=None) -> None:
        v = round(self.speed_var.get(), 2)
        self.speed_label.set(f"{v:.2f}x")
        # length_scale nho = doc NHANH hon
        for d in (self.cfg.en2vi, self.cfg.vi2en):
            d.tts_length_scale = v

    def _on_drop_change(self) -> None:
        for p in self.panels.values():
            if p.pipeline is not None:
                self.apply_latency_settings(p.pipeline)

    def apply_latency_settings(self, pipeline) -> None:
        pipeline.drop_when_behind = self.drop_var.get()
        pipeline.max_lag_s = float(self.maxlag_var.get())

    # ---- thiet bi & canh bao ----

    def refresh_devices(self) -> None:
        loopbacks = list_loopback_devices()
        inputs = list_input_devices()
        outputs = list_output_devices()
        for panel in self.panels.values():
            panel.refresh_devices(loopbacks, inputs, outputs)
        self.check_warnings()

    def check_warnings(self) -> None:
        warnings = []
        src = self.panel_en2vi.selected_source()
        out = self.panel_en2vi.selected_output()

        if src and out and self.panel_en2vi.speak_var.get() and is_same_physical_device(src, out):
            warnings.append(
                "• [Anh->Viet] Phat ban dich ra chinh thiet bi dang bi bat. App se tu tat thu trong luc doc "
                "(khong bi dich chong dich), doi lai vai giay do se khong nghe duoc nguon."
            )

        if self.mode_var.get() == "meeting":
            vi_out = self.panel_vi2en.selected_output()
            if vi_out and src and self.panel_vi2en.speak_var.get() and is_same_physical_device(src, vi_out):
                warnings.append(
                    "⚠ [Viet->Anh] Dang phat tieng Anh vao chinh thiet bi bi bat -> se bi dich nguoc lai sang Viet."
                )

        self.warn_var.set("\n".join(warnings))

    # ---- polling ----

    def _poll(self) -> None:
        try:
            while True:
                self.ui_queue.get_nowait()()
        except queue.Empty:
            pass

        try:
            while True:
                key, msg = self.error_queue.get_nowait()
                panel = self.panels.get(key)
                if panel:
                    panel.status_var.set(f"Loi: {msg[:50]}")
                self.global_status.set(f"Loi ({key}): {msg[:70]}")
        except queue.Empty:
            pass

        try:
            while True:
                status = self.status_queue.get_nowait()
                if status.startswith("[en2vi]"):
                    self.panel_en2vi.status_var.set(status[8:])
                elif status.startswith("[vi2en]"):
                    self.panel_vi2en.status_var.set(status[8:])
                else:
                    self.global_status.set(status)
        except queue.Empty:
            pass

        try:
            while True:
                r = self.result_queue.get_nowait()
                panel = self.panels.get(r.direction_key)
                if panel:
                    panel.append(r)
        except queue.Empty:
            pass

        self.after(POLL_MS, self._poll)

    def destroy(self) -> None:
        for panel in self.panels.values():
            panel.stop()
        super().destroy()


def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()
