import json
import re

import customtkinter as ctk
from tkinter import filedialog
from xtuml_compiler import Simulator, collect_state_machines, compile_text, to_plantuml_state
from xtuml_compiler.diagram import LINE_HEIGHT, build_class_diagram_layout, to_plantuml
from xtuml_compiler.state_diagram import (
    STATE_HEADER_HEIGHT,
    STATE_LINE_HEIGHT,
    build_state_machine_layout,
)


ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


SAMPLES = {
    "xtUML DSL": '''// Model xtUML lengkap dengan state machine
domain Shop {
  datatype Money = real

  class Customer {
    attribute id : string
    attribute name : string

    state machine lifecycle {
      event created
      event activate

      state new initial {
        entry: log("Customer dibuat")
      }
      state active
      state blocked

      transition new -> active on activate when self.name != "" {
        log("diaktifkan")
      }
      transition active -> blocked on created
    }

    operation label() : string {
      return "Customer " + self.name
    }
  }

  class Order {
    attribute total : Money
  }

  association placedOrder between Customer.orders [0..*] and Order.customer [1]

  instance c1 of Customer {
    id = "C-1"
    name = "Alice"
  }
  instance o1 of Order {
    total = 150000
  }
  link c1 to o1 via placedOrder
}
''',
    "xtUML XML": '''<?xml version="1.0"?>
<xtuml name="Shop">
  <class name="Order">
    <attribute name="total" type="real"/>
    <state-machine name="lifecycle">
      <event name="confirm"/>
      <state name="pending" initial="true">
        <entry>log("order baru")</entry>
      </state>
      <state name="paid" final="true"/>
      <transition from="pending" to="paid" event="confirm">
        log("lunas")
      </transition>
    </state-machine>
  </class>
  <instance name="o1" class="Order">
    <attribute name="total">150000</attribute>
  </instance>
</xtuml>
''',
    "PlantUML": '''object user1 {
  name = "Alice"
  age = 28
}

object order1 {
  total = 150000
}

user1 -- order1 : placedOrder
''',
    "JSON": '''{
  "objects": [
    {"name": "user1", "className": "User", "attributes": {"name": "Alice", "age": 28}},
    {"name": "order1", "className": "Order", "attributes": {"total": 150000}}
  ],
  "links": [
    {"from": "user1", "to": "order1", "relation": "placedOrder"}
  ]
}
''',
    "XML": '''<?xml version="1.0"?>
<uml>
  <object id="1" name="user1" class="User">
    <attribute name="name">Alice</attribute>
    <attribute name="age">28</attribute>
  </object>
  <object id="2" name="order1" class="Order">
    <attribute name="total">150000</attribute>
  </object>
  <link source="1" target="2" relation="placedOrder"/>
</uml>
''',
}

FORMAT_MAP = {
    "Auto": "auto",
    "xtUML DSL": "dsl",
    "JSON / IR": "json",
    "XML": "xml",
    "PlantUML": "plantuml",
}
TARGET_MAP = {"Node.js": "node", "Browser": "browser"}

DIAGRAM_BG = "#161b22"
DIAGRAM_CLASS_BODY = "#21262d"
DIAGRAM_CLASS_HEADER = "#2f81f7"
DIAGRAM_DATATYPE_HEADER = "#8957e5"
DIAGRAM_TEXT = "#f0f6fc"
DIAGRAM_MUTED = "#a9b7c6"
DIAGRAM_LINE = "#8b949e"
DIAGRAM_OPERATION = "#79c0ff"

SAMPLE_FORMAT = {
    "xtUML DSL": "xtUML DSL",
    "xtUML XML": "XML",
    "PlantUML": "PlantUML",
    "JSON": "JSON / IR",
    "XML": "XML",
}


class UMLCompilerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("xtUML to JavaScript Compiler")
        self.geometry("1100x880")
        self.minsize(860, 680)
        self.last_result = None
        self.simulator = Simulator()
        self.current_diagram_text = ""
        self.diagram_layout = None
        self.state_machine_entries = []
        self.current_state_diagram_text = ""
        self.state_diagram_layout = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ------------------- HEADER -------------------
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, columnspan=2, padx=20, pady=(15, 5), sticky="ew")

        self.label_title = ctk.CTkLabel(
            self.header_frame,
            text="⚡ xtUML → JavaScript Compiler",
            font=("Segoe UI", 22, "bold"),
        )
        self.label_title.pack(side="left")

        self.label_subtitle = ctk.CTkLabel(
            self.header_frame,
            text="Parser → IR → Validator → Generator JS + runtime",
            font=("Segoe UI", 12),
            text_color="gray",
        )
        self.label_subtitle.pack(side="left", padx=15, pady=(5, 0))

        # ------------------- TOOLBAR -------------------
        self.toolbar_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.toolbar_frame.grid(row=1, column=0, columnspan=2, padx=20, pady=5, sticky="ew")

        self.sample_option = ctk.CTkOptionMenu(
            self.toolbar_frame,
            values=["Muat Contoh Input...", *SAMPLES.keys()],
            command=self.load_sample,
        )
        self.sample_option.pack(side="left", padx=(0, 10))

        self.format_option = ctk.CTkOptionMenu(
            self.toolbar_frame,
            values=list(FORMAT_MAP.keys()),
            width=110,
        )
        self.format_option.pack(side="left", padx=(0, 10))

        self.target_option = ctk.CTkOptionMenu(
            self.toolbar_frame,
            values=list(TARGET_MAP.keys()),
            width=100,
        )
        self.target_option.pack(side="left")

        self.btn_clear = ctk.CTkButton(
            self.toolbar_frame,
            text="🗑️ Bersihkan",
            fg_color="#e74c3c",
            hover_color="#c0392b",
            width=100,
            command=self.clear_all,
        )
        self.btn_clear.pack(side="left", padx=(10, 0))

        self.btn_ir = ctk.CTkButton(
            self.toolbar_frame,
            text="🧾 Simpan IR",
            width=110,
            command=self.save_ir,
        )
        self.btn_ir.pack(side="right", padx=(10, 0))

        self.btn_copy = ctk.CTkButton(
            self.toolbar_frame,
            text="📋 Salin JS",
            width=110,
            command=self.copy_output,
        )
        self.btn_copy.pack(side="right", padx=(10, 0))

        self.btn_save = ctk.CTkButton(
            self.toolbar_frame,
            text="💾 Simpan .js",
            fg_color="#27ae60",
            hover_color="#219150",
            width=110,
            command=self.save_to_file,
        )
        self.btn_save.pack(side="right")

        # ------------------- EDITOR -------------------
        self.input_frame = ctk.CTkFrame(self)
        self.input_frame.grid(row=2, column=0, padx=(20, 10), pady=10, sticky="nsew")
        self.input_frame.grid_rowconfigure(1, weight=1)
        self.input_frame.grid_columnconfigure(0, weight=1)

        self.input_label = ctk.CTkLabel(
            self.input_frame,
            text="Model xtUML (DSL / XML / JSON / PlantUML):",
            font=("Segoe UI", 13, "bold"),
        )
        self.input_label.grid(row=0, column=0, sticky="w", padx=10, pady=5)

        self.txt_input = ctk.CTkTextbox(self.input_frame, font=("Consolas", 13), wrap="none")
        self.txt_input.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")

        self.output_frame = ctk.CTkFrame(self)
        self.output_frame.grid(row=2, column=1, padx=(10, 20), pady=10, sticky="nsew")
        self.output_frame.grid_rowconfigure(1, weight=1)
        self.output_frame.grid_columnconfigure(0, weight=1)

        self.output_label = ctk.CTkLabel(
            self.output_frame,
            text="Hasil:",
            font=("Segoe UI", 13, "bold"),
        )
        self.output_label.grid(row=0, column=0, sticky="w", padx=10, pady=5)

        self.output_tabs = ctk.CTkTabview(self.output_frame)
        self.output_tabs.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")

        js_tab = self.output_tabs.add("JavaScript")
        diagram_tab = self.output_tabs.add("Class Diagram")
        js_tab.grid_rowconfigure(0, weight=1)
        js_tab.grid_columnconfigure(0, weight=1)
        diagram_tab.grid_rowconfigure(1, weight=1)
        diagram_tab.grid_columnconfigure(0, weight=1)

        self.txt_output = ctk.CTkTextbox(js_tab, font=("Consolas", 13), wrap="none")
        self.txt_output.grid(row=0, column=0, sticky="nsew")

        self.diagram_controls = ctk.CTkFrame(diagram_tab, fg_color="transparent")
        self.diagram_controls.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(6, 4))
        self.btn_diagram_copy = ctk.CTkButton(
            self.diagram_controls,
            text="📋 Salin PUML",
            width=110,
            command=self.copy_diagram,
        )
        self.btn_diagram_copy.pack(side="left", padx=(6, 4))
        self.btn_diagram_save = ctk.CTkButton(
            self.diagram_controls,
            text="💾 Simpan .puml",
            width=120,
            command=self.save_diagram,
        )
        self.btn_diagram_save.pack(side="left", padx=4)
        self.lbl_diagram_info = ctk.CTkLabel(
            self.diagram_controls, text="Belum ada diagram", font=("Segoe UI", 11), text_color="gray"
        )
        self.lbl_diagram_info.pack(side="left", padx=8)

        self.canvas_diagram = ctk.CTkCanvas(diagram_tab, bg=DIAGRAM_BG, highlightthickness=0)
        self.canvas_diagram.grid(row=1, column=0, sticky="nsew")
        self.scroll_y = ctk.CTkScrollbar(diagram_tab, command=self.canvas_diagram.yview)
        self.scroll_y.grid(row=1, column=1, sticky="ns")
        self.scroll_x = ctk.CTkScrollbar(
            diagram_tab, orientation="horizontal", command=self.canvas_diagram.xview
        )
        self.scroll_x.grid(row=2, column=0, sticky="ew")
        self.canvas_diagram.configure(
            xscrollcommand=self.scroll_x.set, yscrollcommand=self.scroll_y.set
        )
        self.canvas_diagram.bind(
            "<Configure>", lambda _event: self._update_diagram_scrollregion()
        )
        self.clear_diagram("Kompile model dulu untuk melihat class diagram.")

        state_tab = self.output_tabs.add("State Diagram")
        state_tab.grid_rowconfigure(1, weight=1)
        state_tab.grid_columnconfigure(0, weight=1)

        self.state_controls = ctk.CTkFrame(state_tab, fg_color="transparent")
        self.state_controls.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(6, 4))
        ctk.CTkLabel(
            self.state_controls, text="State machine:", font=("Segoe UI", 11), text_color="gray"
        ).pack(side="left", padx=(6, 4))
        self.state_machine_option = ctk.CTkOptionMenu(
            self.state_controls, values=["-"], width=160, command=self.on_state_machine_selected
        )
        self.state_machine_option.pack(side="left", padx=4)
        self.btn_state_copy = ctk.CTkButton(
            self.state_controls,
            text="📋 Salin PUML",
            width=110,
            command=self.copy_state_diagram,
        )
        self.btn_state_copy.pack(side="left", padx=(8, 4))
        self.btn_state_save = ctk.CTkButton(
            self.state_controls,
            text="💾 Simpan .puml",
            width=120,
            command=self.save_state_diagram,
        )
        self.btn_state_save.pack(side="left", padx=4)
        self.lbl_state_info = ctk.CTkLabel(
            self.state_controls, text="Belum ada state machine", font=("Segoe UI", 11), text_color="gray"
        )
        self.lbl_state_info.pack(side="left", padx=8)

        self.canvas_state = ctk.CTkCanvas(state_tab, bg=DIAGRAM_BG, highlightthickness=0)
        self.canvas_state.grid(row=1, column=0, sticky="nsew")
        self.scroll_state_y = ctk.CTkScrollbar(state_tab, command=self.canvas_state.yview)
        self.scroll_state_y.grid(row=1, column=1, sticky="ns")
        self.scroll_state_x = ctk.CTkScrollbar(
            state_tab, orientation="horizontal", command=self.canvas_state.xview
        )
        self.scroll_state_x.grid(row=2, column=0, sticky="ew")
        self.canvas_state.configure(
            xscrollcommand=self.scroll_state_x.set, yscrollcommand=self.scroll_state_y.set
        )
        self.canvas_state.bind(
            "<Configure>", lambda _event: self._update_state_scrollregion()
        )
        self.clear_state_diagram("Kompile model dulu untuk melihat state diagram.")

        # ------------------- DIAGNOSTICS / SIMULATOR -------------------
        self.bottom_tabs = ctk.CTkTabview(self, height=190)
        self.bottom_tabs.grid(row=3, column=0, columnspan=2, padx=20, pady=(0, 10), sticky="ew")

        diagnostic_tab = self.bottom_tabs.add("Diagnostics")
        diagnostic_tab.grid_columnconfigure(0, weight=1)
        diagnostic_tab.grid_rowconfigure(0, weight=1)

        self.txt_diagnostic = ctk.CTkTextbox(
            diagnostic_tab, height=130, font=("Consolas", 12), wrap="word"
        )
        self.txt_diagnostic.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.txt_diagnostic.bind("<Double-Button-1>", lambda _event: self.jump_to_diagnostic())
        self.txt_input.tag_config("diag_error", background="#5c2b2b", foreground="#ffdddd")
        self.txt_input.tag_config("diag_warning", background="#5c4a1f", foreground="#ffe6a8")

        sim_tab = self.bottom_tabs.add("Simulator")
        sim_tab.grid_columnconfigure(1, weight=1)
        sim_tab.grid_rowconfigure(0, weight=1)

        self.sim_control = ctk.CTkFrame(sim_tab, fg_color="transparent")
        self.sim_control.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="nw")

        self.lbl_sim_status = ctk.CTkLabel(
            self.sim_control,
            text="Simulator belum dijalankan. Compile model dulu.",
            font=("Segoe UI", 11),
            anchor="w",
        )
        self.lbl_sim_status.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 5))

        self.sim_instance = ctk.CTkOptionMenu(
            self.sim_control, values=["-"], width=130, command=self.on_instance_selected
        )
        self.sim_instance.grid(row=1, column=0, padx=(0, 5), pady=2, sticky="w")

        self.sim_event = ctk.CTkOptionMenu(self.sim_control, values=["-"], width=120)
        self.sim_event.grid(row=1, column=1, padx=5, pady=2, sticky="w")

        self.sim_payload = ctk.CTkEntry(
            self.sim_control, placeholder_text="Payload JSON (opsional)", width=180
        )
        self.sim_payload.grid(row=1, column=2, padx=(5, 0), pady=2, sticky="w")

        self.btn_send = ctk.CTkButton(
            self.sim_control, text="📤 Kirim Event", width=120, command=self.send_event
        )
        self.btn_send.grid(row=2, column=0, padx=(0, 5), pady=(8, 0), sticky="w")

        self.btn_refresh = ctk.CTkButton(
            self.sim_control, text="🔄 Refresh", width=90, command=self.refresh_simulator
        )
        self.btn_refresh.grid(row=2, column=1, padx=5, pady=(8, 0), sticky="w")

        self.btn_sim_reset = ctk.CTkButton(
            self.sim_control, text="↺ Reset", width=80, command=self.reset_simulator
        )
        self.btn_sim_reset.grid(row=2, column=2, padx=(5, 0), pady=(8, 0), sticky="w")

        self.txt_sim = ctk.CTkTextbox(sim_tab, font=("Consolas", 12), wrap="none")
        self.txt_sim.grid(row=0, column=1, padx=(5, 10), pady=10, sticky="nsew")
        self.bottom_tabs.set("Diagnostics")

        # ------------------- COMPILE -------------------
        self.btn_compile = ctk.CTkButton(
            self,
            text="🚀 Compile ke JavaScript   (Ctrl+Enter)",
            font=("Segoe UI", 14, "bold"),
            height=42,
            command=self.on_compile,
        )
        self.btn_compile.grid(row=4, column=0, columnspan=2, padx=20, pady=5, sticky="ew")

        self.lbl_status = ctk.CTkLabel(
            self,
            text="Siap. Muat contoh atau masukkan model xtUML Anda.",
            font=("Segoe UI", 11),
            anchor="w",
            text_color="gray",
        )
        self.lbl_status.grid(row=5, column=0, columnspan=2, padx=20, pady=(0, 10), sticky="ew")

        self.bind("<Control-Return>", lambda _event: self.on_compile())

    # ------------------- EVENT HANDLERS -------------------
    def on_compile(self):
        source = self.txt_input.get("0.0", "end")
        source_format = FORMAT_MAP.get(self.format_option.get(), "auto")
        target = TARGET_MAP.get(self.target_option.get(), "node")
        result = compile_text(source, format=source_format, target=target, source="<editor>")
        self.last_result = result

        self.txt_output.delete("0.0", "end")
        if result.ok:
            self.txt_output.insert("0.0", result.js)
            self.render_class_diagram(result.model)
            self.populate_state_machines(result.model)
        else:
            self.clear_diagram("Compile gagal. Perbaiki model lalu compile ulang.")
            self.clear_state_diagram("Compile gagal. Perbaiki model lalu compile ulang.")

        self.txt_diagnostic.delete("0.0", "end")
        self.txt_diagnostic.insert("0.0", result.message)
        self.highlight_diagnostics(result)

        if result.ok:
            started, sim_message = self.start_simulator()
            simulator_note = "" if started else f" • simulator: {sim_message}"
            if result.diagnostics.warnings:
                self.set_status(
                    f"✅ Berhasil dicompile dengan {len(result.diagnostics.warnings)} "
                    f"peringatan.{simulator_note}",
                    color="#f39c12",
                )
            else:
                self.set_status(
                    f"✅ Berhasil dicompile ke JavaScript!{simulator_note}", color="#2ecc71"
                )
        else:
            self.simulator.stop()
            self.lbl_sim_status.configure(text="Simulator tidak aktif (compile gagal).")
            self.txt_sim.delete("0.0", "end")
            errors = len(result.diagnostics.errors)
            self.set_status(f"❌ Compile gagal ({errors} error). Lihat Diagnostics.", color="#e74c3c")

    # ------------------- CLASS DIAGRAM -------------------
    def clear_diagram(self, message: str = ""):
        self.canvas_diagram.delete("all")
        self.current_diagram_text = ""
        self.diagram_layout = None
        self.lbl_diagram_info.configure(text="Belum ada diagram")
        text = message or "Tidak ada class diagram untuk ditampilkan."
        self.canvas_diagram.create_text(
            20,
            20,
            anchor="nw",
            text=text,
            fill=DIAGRAM_MUTED,
            font=("Segoe UI", 12),
            width=520,
        )
        self._update_diagram_scrollregion()

    def _update_diagram_scrollregion(self):
        canvas = self.canvas_diagram
        width = float(self.diagram_layout.width) if self.diagram_layout else 0.0
        height = float(self.diagram_layout.height) if self.diagram_layout else 0.0
        width = max(width, float(canvas.winfo_width() or 1))
        height = max(height, float(canvas.winfo_height() or 1))
        canvas.configure(scrollregion=(0, 0, width, height))

    def render_class_diagram(self, model):
        layout = build_class_diagram_layout(model) if model else None
        self.diagram_layout = layout
        self.current_diagram_text = to_plantuml(model) if model else ""
        self.canvas_diagram.delete("all")
        if layout is None or layout.is_empty:
            self.clear_diagram("Model tidak memiliki class untuk ditampilkan.")
            return

        cardinalities = [edge.cardinality for edge in layout.edges if edge.cardinality]
        summary = f" ({', '.join(cardinalities)})" if cardinalities else ""
        self.lbl_diagram_info.configure(
            text=f"{len(layout.classes)} class • {len(layout.edges)} relasi{summary}"
        )
        self._draw_diagram_edges(layout)
        self._draw_diagram_classes(layout)
        self._draw_diagram_labels(layout)
        self._update_diagram_scrollregion()

    def _draw_diagram_edges(self, layout):
        for edge in layout.edges:
            if edge.kind == "generalization":
                self.canvas_diagram.create_line(
                    edge.x1, edge.y1, edge.x2, edge.y2, fill=DIAGRAM_LINE, width=2
                )
            elif edge.source == edge.target:
                loop_y = edge.y1 + 34
                self.canvas_diagram.create_line(
                    edge.x1,
                    edge.y1,
                    edge.x1,
                    loop_y,
                    edge.x2,
                    loop_y,
                    edge.x2,
                    edge.y2,
                    fill=DIAGRAM_LINE,
                    width=2,
                    smooth=True,
                )
            else:
                self.canvas_diagram.create_line(
                    edge.x1, edge.y1, edge.x2, edge.y2, fill=DIAGRAM_LINE, width=2
                )

    def _draw_diagram_classes(self, layout):
        for box in layout.classes:
            header = DIAGRAM_DATATYPE_HEADER if box.stereotype else DIAGRAM_CLASS_HEADER
            self.canvas_diagram.create_rectangle(
                box.x,
                box.y,
                box.x + box.width,
                box.y + box.height,
                fill=DIAGRAM_CLASS_BODY,
                outline=DIAGRAM_LINE,
                width=2,
            )
            self.canvas_diagram.create_rectangle(
                box.x,
                box.y,
                box.x + box.width,
                box.y + box.header_height,
                fill=header,
                outline="",
            )
            self.canvas_diagram.create_line(
                box.x,
                box.y + box.header_height,
                box.x + box.width,
                box.y + box.header_height,
                fill=DIAGRAM_LINE,
            )
            title = box.name + ("  «datatype»" if box.stereotype else "")
            self.canvas_diagram.create_text(
                box.x + box.width / 2,
                box.y + box.header_height / 2,
                text=title,
                fill="#ffffff",
                font=("Segoe UI", 11, "bold"),
            )

            text_y = box.y + box.header_height + 10
            for attribute in box.attributes:
                self.canvas_diagram.create_text(
                    box.x + 10,
                    text_y,
                    anchor="w",
                    text=f"+ {attribute}",
                    fill=DIAGRAM_TEXT,
                    font=("Consolas", 10),
                )
                text_y += LINE_HEIGHT
            if box.attributes and box.operations:
                self.canvas_diagram.create_line(
                    box.x + 8, text_y - 5, box.x + box.width - 8, text_y - 5, fill=DIAGRAM_MUTED
                )
                text_y += 4
            for operation in box.operations:
                self.canvas_diagram.create_text(
                    box.x + 10,
                    text_y,
                    anchor="w",
                    text=f"+ {operation}",
                    fill=DIAGRAM_OPERATION,
                    font=("Consolas", 10),
                )
                text_y += LINE_HEIGHT

    def _draw_diagram_labels(self, layout):
        for edge in layout.edges:
            if edge.kind == "generalization":
                self._draw_diagram_arrow(edge.x2, edge.y2, edge.target_side)
                continue

            label_x = (edge.x1 + edge.x2) / 2
            label_y = (edge.y1 + edge.y2) / 2
            if edge.source == edge.target:
                label_y = edge.y1 + 58
            if edge.cardinality:
                self.canvas_diagram.create_text(
                    label_x,
                    label_y - 15,
                    text=f"[{edge.cardinality}]",
                    fill=DIAGRAM_OPERATION,
                    font=("Consolas", 9, "bold"),
                    bbox=dict(fill=DIAGRAM_BG, outline=DIAGRAM_OPERATION),
                )
            if edge.label:
                self.canvas_diagram.create_text(
                    label_x,
                    label_y,
                    text=edge.label,
                    fill=DIAGRAM_TEXT,
                    font=("Consolas", 10, "bold"),
                    bbox=dict(fill=DIAGRAM_BG, outline=""),
                )
            self._draw_diagram_multiplicity(
                edge.x1, edge.y1, edge.source_side, edge.source_multiplicity
            )
            self._draw_diagram_multiplicity(
                edge.x2, edge.y2, edge.target_side, edge.target_multiplicity
            )

    def _draw_diagram_multiplicity(self, x, y, side, value):
        if not value:
            return
        offsets = {
            "left": (-6, 0, "e"),
            "right": (6, 0, "w"),
            "top": (0, -6, "s"),
            "bottom": (0, 6, "n"),
        }
        offset_x, offset_y, anchor = offsets.get(side, (0, 0, "center"))
        self.canvas_diagram.create_text(
            x + offset_x,
            y + offset_y,
            anchor=anchor,
            text=value,
            fill=DIAGRAM_MUTED,
            font=("Consolas", 9, "bold"),
        )

    def _draw_diagram_arrow(self, x, y, side):
        points = {
            "left": [(x, y), (x + 11, y - 6), (x + 11, y + 6)],
            "right": [(x, y), (x - 11, y - 6), (x - 11, y + 6)],
            "top": [(x, y), (x - 6, y + 11), (x + 6, y + 11)],
            "bottom": [(x, y), (x - 6, y - 11), (x + 6, y - 11)],
        }.get(side)
        if not points:
            return
        self.canvas_diagram.create_polygon(
            *(coord for point in points for coord in point),
            fill=DIAGRAM_LINE,
            outline=DIAGRAM_LINE,
        )

    def copy_diagram(self):
        text = self.current_diagram_text.strip()
        if not text:
            self.set_status("⚠️ Compile model dulu untuk menyalin class diagram.", color="#e67e22")
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.set_status("📋 Class diagram PlantUML disalin ke clipboard!", color="#3498db")

    def save_diagram(self):
        text = self.current_diagram_text.strip()
        if not text:
            self.set_status("⚠️ Compile model dulu untuk menyimpan class diagram.", color="#e67e22")
            return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".puml",
            filetypes=[("PlantUML Files", "*.puml"), ("All Files", "*.*")],
        )
        if file_path:
            with open(file_path, "w", encoding="utf-8") as handle:
                handle.write(text)
            self.set_status(f"💾 Class diagram disimpan di: {file_path}", color="#2ecc71")

    # ------------------- STATE DIAGRAM -------------------
    def clear_state_diagram(self, message: str = ""):
        self.canvas_state.delete("all")
        self.state_diagram_layout = None
        self.current_state_diagram_text = ""
        self.state_machine_entries = []
        self.state_machine_option.configure(values=["-"])
        self.state_machine_option.set("-")
        self.lbl_state_info.configure(text="Belum ada state machine")
        text = message or "Tidak ada state diagram untuk ditampilkan."
        self.canvas_state.create_text(
            20,
            20,
            anchor="nw",
            text=text,
            fill=DIAGRAM_MUTED,
            font=("Segoe UI", 12),
            width=520,
        )
        self._update_state_scrollregion()

    def _update_state_scrollregion(self):
        canvas = self.canvas_state
        width = float(self.state_diagram_layout.width) if self.state_diagram_layout else 0.0
        height = float(self.state_diagram_layout.height) if self.state_diagram_layout else 0.0
        width = max(width, float(canvas.winfo_width() or 1))
        height = max(height, float(canvas.winfo_height() or 1))
        canvas.configure(scrollregion=(0, 0, width, height))

    def populate_state_machines(self, model):
        entries = collect_state_machines(model) if model else []
        self.state_machine_entries = entries
        labels = [f"{class_name}.{machine.name}" for class_name, machine in entries]
        self.state_machine_option.configure(values=labels or ["-"])
        if labels:
            self.state_machine_option.set(labels[0])
            self.on_state_machine_selected(labels[0])
        else:
            self.clear_state_diagram("Model tidak memiliki state machine.")

    def on_state_machine_selected(self, name):
        for class_name, machine in self.state_machine_entries:
            if f"{class_name}.{machine.name}" == name:
                self.current_state_diagram_text = to_plantuml_state(machine, class_name)
                self.render_state_diagram(machine, class_name)
                return
        self.clear_state_diagram("Pilih state machine yang valid.")

    def render_state_diagram(self, machine, class_name):
        layout = build_state_machine_layout(machine)
        self.state_diagram_layout = layout
        self.canvas_state.delete("all")
        if layout.is_empty:
            self.clear_state_diagram("State machine tidak memiliki state.")
            return

        state_names = {node.name for node in layout.nodes if not node.pseudo}
        transitions = [edge for edge in layout.edges if edge.kind == "transition"]
        self.lbl_state_info.configure(
            text=f"{len(state_names)} state • {len(transitions)} transisi"
        )
        self._draw_state_edges(layout)
        self._draw_state_nodes(layout)
        self._draw_state_labels(layout)
        self._update_state_scrollregion()

    def _draw_state_edges(self, layout):
        for edge in layout.edges:
            if edge.is_self:
                loop_y = edge.y1 + 38
                self.canvas_state.create_line(
                    edge.x1,
                    edge.y1,
                    edge.x1,
                    loop_y,
                    edge.x2,
                    loop_y,
                    edge.x2,
                    edge.y2,
                    fill=DIAGRAM_LINE,
                    width=2,
                    smooth=True,
                )
            else:
                self.canvas_state.create_line(
                    edge.x1, edge.y1, edge.x2, edge.y2, fill=DIAGRAM_LINE, width=2
                )

    def _draw_state_nodes(self, layout):
        for node in layout.nodes:
            if node.pseudo:
                self.canvas_state.create_oval(
                    node.x,
                    node.y,
                    node.x + node.width,
                    node.y + node.height,
                    fill=DIAGRAM_TEXT,
                    outline=DIAGRAM_TEXT,
                )
                continue

            if node.final:
                self.canvas_state.create_oval(
                    node.x,
                    node.y,
                    node.x + node.width,
                    node.y + node.height,
                    fill=DIAGRAM_CLASS_BODY,
                    outline=DIAGRAM_LINE,
                    width=2,
                )
                self.canvas_state.create_oval(
                    node.x + 5,
                    node.y + 5,
                    node.x + node.width - 5,
                    node.y + node.height - 5,
                    fill=DIAGRAM_CLASS_BODY,
                    outline=DIAGRAM_LINE,
                    width=2,
                )
            else:
                self.canvas_state.create_rectangle(
                    node.x,
                    node.y,
                    node.x + node.width,
                    node.y + node.height,
                    fill=DIAGRAM_CLASS_BODY,
                    outline=DIAGRAM_LINE,
                    width=2,
                )

            self.canvas_state.create_text(
                node.x + node.width / 2,
                node.y + STATE_HEADER_HEIGHT / 2,
                text=node.name,
                fill="#ffffff",
                font=("Segoe UI", 11, "bold"),
            )
            text_y = node.y + STATE_HEADER_HEIGHT + 4
            for action in node.entry:
                self.canvas_state.create_text(
                    node.x + 8,
                    text_y,
                    anchor="w",
                    text=f"entry / {action}",
                    fill=DIAGRAM_OPERATION,
                    font=("Consolas", 9),
                )
                text_y += STATE_LINE_HEIGHT
            for action in node.exit:
                self.canvas_state.create_text(
                    node.x + 8,
                    text_y,
                    anchor="w",
                    text=f"exit / {action}",
                    fill=DIAGRAM_MUTED,
                    font=("Consolas", 9),
                )
                text_y += STATE_LINE_HEIGHT

    def _draw_state_labels(self, layout):
        for edge in layout.edges:
            label_x = (edge.x1 + edge.x2) / 2
            label_y = (edge.y1 + edge.y2) / 2
            if edge.is_self:
                label_y = edge.y1 + 42
            if edge.label:
                self.canvas_state.create_text(
                    label_x,
                    label_y,
                    text=edge.label,
                    fill=DIAGRAM_TEXT,
                    font=("Consolas", 10, "bold"),
                    bbox=dict(fill=DIAGRAM_BG, outline=""),
                )
            self._draw_state_arrow(edge.x2, edge.y2, edge.target_side)

    def _draw_state_arrow(self, x, y, side):
        points = {
            "left": [(x, y), (x + 11, y - 6), (x + 11, y + 6)],
            "right": [(x, y), (x - 11, y - 6), (x - 11, y + 6)],
            "top": [(x, y), (x - 6, y + 11), (x + 6, y + 11)],
            "bottom": [(x, y), (x - 6, y - 11), (x + 6, y - 11)],
        }.get(side)
        if not points:
            return
        self.canvas_state.create_polygon(
            *(coord for point in points for coord in point),
            fill=DIAGRAM_LINE,
            outline=DIAGRAM_LINE,
        )

    def copy_state_diagram(self):
        text = self.current_state_diagram_text.strip()
        if not text:
            self.set_status("⚠️ Compile model dulu untuk menyalin state diagram.", color="#e67e22")
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.set_status("📋 State diagram PlantUML disalin ke clipboard!", color="#3498db")

    def save_state_diagram(self):
        text = self.current_state_diagram_text.strip()
        if not text:
            self.set_status("⚠️ Compile model dulu untuk menyimpan state diagram.", color="#e67e22")
            return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".puml",
            filetypes=[("PlantUML Files", "*.puml"), ("All Files", "*.*")],
        )
        if file_path:
            with open(file_path, "w", encoding="utf-8") as handle:
                handle.write(text)
            self.set_status(f"💾 State diagram disimpan di: {file_path}", color="#2ecc71")

    # ------------------- DIAGNOSTICS -------------------
    def highlight_diagnostics(self, result):
        for tag in ("diag_error", "diag_warning"):
            self.txt_input.tag_remove(tag, "0.0", "end")
        last_line = max(1, int(self.txt_input.index("end-1c").split(".")[0]))
        for item in result.diagnostics.items:
            if not item.line:
                continue
            line = min(max(1, item.line), last_line)
            tag = "diag_error" if item.severity == "error" else "diag_warning"
            self.txt_input.tag_add(tag, f"{line}.0", f"{line}.end")

    def jump_to_diagnostic(self):
        line_text = self.txt_diagnostic.get("insert linestart", "insert lineend")
        match = re.search(r":(\d+)(?::\d+)?:", line_text)
        if not match:
            match = re.search(r"^\s*\[[A-Z]+\]\s*(\d+)(?::\d+)?:", line_text)
        if not match:
            return
        target = int(match.group(1))
        last_line = max(1, int(self.txt_input.index("end-1c").split(".")[0]))
        if target > last_line:
            return
        self.txt_input.mark_set("insert", f"{target}.0")
        self.txt_input.see("insert")
        self.txt_input.focus_set()

    # ------------------- SIMULATOR -------------------
    def start_simulator(self):
        if not self.last_result:
            return False, "belum ada hasil compile"
        started, message = self.simulator.start(self.last_result.js)
        color = "#2ecc71" if started else "#e67e22"
        self.lbl_sim_status.configure(text=message, text_color=color)
        if not started:
            self.txt_sim.delete("0.0", "end")
            self.txt_sim.insert("0.0", message)
            return False, message

        snapshot = self.simulator.snapshot()
        instances = [item["name"] for item in snapshot.get("instances", [])]
        self.sim_instance.configure(values=instances or ["-"])
        if instances:
            self.sim_instance.set(instances[0])
            self.on_instance_selected(instances[0])
        else:
            self.sim_event.configure(values=["-"])
            self.sim_event.set("-")
        self.show_snapshot(snapshot)
        return True, message

    def on_instance_selected(self, name):
        if not self.simulator.running:
            return
        reply = self.simulator.events(name)
        events = reply.get("events", []) if reply.get("ok") else []
        self.sim_event.configure(values=events or ["-"])
        self.sim_event.set(events[0] if events else "-")

    def show_snapshot(self, snapshot, extra_logs=None):
        if not snapshot.get("ok"):
            self.txt_sim.delete("0.0", "end")
            self.txt_sim.insert("0.0", str(snapshot.get("error", "Snapshot gagal")))
            return
        data = {key: value for key, value in snapshot.items() if key != "logs"}
        text = json.dumps(data, indent=2, ensure_ascii=False)
        logs = list(snapshot.get("logs") or []) + list(extra_logs or [])
        if logs:
            text += "\n\n--- console.log ---\n" + "\n".join(logs)
        self.txt_sim.delete("0.0", "end")
        self.txt_sim.insert("0.0", text)

    def refresh_simulator(self):
        if not self.simulator.running:
            self.set_status("⚠️ Simulator belum berjalan.", color="#e67e22")
            return
        self.show_snapshot(self.simulator.snapshot())
        self.set_status("🔄 State simulator diperbarui.", color="#3498db")

    def send_event(self):
        if not self.simulator.running:
            self.set_status("⚠️ Simulator belum berjalan.", color="#e67e22")
            return
        instance = self.sim_instance.get()
        event = self.sim_event.get()
        if instance == "-" or event == "-":
            self.set_status("⚠️ Pilih instance dan event terlebih dahulu.", color="#e67e22")
            return
        payload_text = self.sim_payload.get().strip()
        payload = None
        if payload_text:
            try:
                payload = json.loads(payload_text)
            except json.JSONDecodeError as exc:
                self.set_status(f"❌ Payload JSON tidak valid: {exc}", color="#e74c3c")
                return

        reply = self.simulator.send(instance, event, payload)
        if not reply.get("ok"):
            self.set_status(f"❌ {reply.get('error')}", color="#e74c3c")
            return
        self.show_snapshot(self.simulator.snapshot(), reply.get("logs") or [])
        handled = "ditangani" if reply.get("handled") else "tidak ditangani"
        self.set_status(
            f"⚡ Event {event} {handled}; state = {reply.get('state')}", color="#3498db"
        )

    def reset_simulator(self):
        if not self.simulator.running:
            self.set_status("⚠️ Simulator belum berjalan.", color="#e67e22")
            return
        instance = self.sim_instance.get()
        if instance == "-":
            return
        reply = self.simulator.reset(instance)
        if reply.get("ok"):
            self.show_snapshot(self.simulator.snapshot(), reply.get("logs") or [])
            self.set_status(f"↺ State {instance} di-reset.", color="#3498db")
        else:
            self.set_status(f"❌ {reply.get('error')}", color="#e74c3c")

    def load_sample(self, choice):
        if choice not in SAMPLES:
            return
        self.txt_input.delete("0.0", "end")
        self.txt_input.insert("0.0", SAMPLES[choice])
        self.format_option.set(SAMPLE_FORMAT.get(choice, "Auto"))
        self.set_status(f"Memuat contoh format {choice}.", color="gray")
        self.sample_option.set("Muat Contoh Input...")

    def clear_all(self):
        self.txt_input.delete("0.0", "end")
        self.txt_output.delete("0.0", "end")
        self.clear_diagram()
        self.clear_state_diagram()
        self.txt_diagnostic.delete("0.0", "end")
        for tag in ("diag_error", "diag_warning"):
            self.txt_input.tag_remove(tag, "0.0", "end")
        self.simulator.stop()
        self.lbl_sim_status.configure(
            text="Simulator belum dijalankan. Compile model dulu.", text_color="gray"
        )
        self.txt_sim.delete("0.0", "end")
        self.sim_instance.configure(values=["-"])
        self.sim_instance.set("-")
        self.sim_event.configure(values=["-"])
        self.sim_event.set("-")
        self.last_result = None
        self.set_status("Layar telah dibersihkan.", color="gray")

    def copy_output(self):
        output_text = self.txt_output.get("0.0", "end").strip()
        if output_text:
            self.clipboard_clear()
            self.clipboard_append(output_text)
            self.set_status("📋 Kode JavaScript berhasil disalin ke clipboard!", color="#3498db")
        else:
            self.set_status("⚠️ Tidak ada kode JavaScript untuk disalin.", color="#e67e22")

    def save_to_file(self):
        output_text = self.txt_output.get("0.0", "end").strip()
        if not output_text:
            self.set_status("⚠️ Tidak ada hasil compile untuk disimpan.", color="#e67e22")
            return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".js",
            filetypes=[("JavaScript Files", "*.js"), ("All Files", "*.*")],
        )
        if file_path:
            with open(file_path, "w", encoding="utf-8") as handle:
                handle.write(output_text)
            self.set_status(f"💾 File berhasil disimpan di: {file_path}", color="#2ecc71")

    def save_ir(self):
        if not self.last_result or not self.last_result.ir_json:
            self.set_status("⚠️ Compile model terlebih dahulu sebelum menyimpan IR.", color="#e67e22")
            return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
        )
        if file_path:
            with open(file_path, "w", encoding="utf-8") as handle:
                handle.write(self.last_result.ir_json)
            self.set_status(f"🧾 IR disimpan di: {file_path}", color="#2ecc71")

    def set_status(self, message, color="gray"):
        self.lbl_status.configure(text=message, text_color=color)


if __name__ == "__main__":
    app = UMLCompilerApp()
    app.mainloop()
