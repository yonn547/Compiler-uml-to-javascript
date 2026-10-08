import customtkinter as ctk
from tkinter import filedialog
from compiler import compile_uml_to_js

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

# Template Contoh Input jika pengguna ingin memuat sampel
SAMPLES = {
    "PlantUML": 'object user1 {\n  name = "Alice"\n  age = 28\n}\n\nobject order1 {\n  total = 150000\n}\n\nuser1 -- order1 : placedOrder',
    "JSON": '{\n  "objects": [\n    {"name": "user1", "className": "User", "attributes": {"name": "Alice", "age": 28}},\n    {"name": "order1", "className": "Order", "attributes": {"total": 150000}}\n  ],\n  "links": [\n    {"from": "user1", "to": "order1", "relation": "placedOrder"}\n  ]\n}',
    "XML": '<?xml version="1.0"?>\n<uml>\n  <object id="1" name="user1" class="User">\n    <attribute name="name">Alice</attribute>\n    <attribute name="age">28</attribute>\n  </object>\n  <object id="2" name="order1" class="Order">\n    <attribute name="total">150000</attribute>\n  </object>\n  <link source="1" target="2" relation="placedOrder"/>\n</uml>'
}

class UMLCompilerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("UML Object Diagram to JavaScript Compiler")
        self.geometry("1000x680")
        self.minsize(800, 500)

        # Layout Grid Utama
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ------------------- HEADER -------------------
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, columnspan=2, padx=20, pady=(15, 5), sticky="ew")

        self.label_title = ctk.CTkLabel(
            self.header_frame, 
            text="⚡ UML to JavaScript Compiler", 
            font=("Segoe UI", 22, "bold")
        )
        self.label_title.pack(side="left")

        self.label_subtitle = ctk.CTkLabel(
            self.header_frame, 
            text="Mendukung format PlantUML, JSON, dan XML", 
            font=("Segoe UI", 12),
            text_color="gray"
        )
        self.label_subtitle.pack(side="left", padx=15, pady=(5, 0))

        # ------------------- TOOLBAR / ACTION BAR -------------------
        self.toolbar_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.toolbar_frame.grid(row=1, column=0, columnspan=2, padx=20, pady=5, sticky="ew")

        # Load Sample Dropdown
        self.sample_option = ctk.CTkOptionMenu(
            self.toolbar_frame, 
            values=["Muat Contoh Input...", "PlantUML", "JSON", "XML"],
            command=self.load_sample
        )
        self.sample_option.pack(side="left", padx=(0, 10))

        # Clear Button
        self.btn_clear = ctk.CTkButton(
            self.toolbar_frame, 
            text="🗑️ Bersihkan", 
            fg_color="#e74c3c", 
            hover_color="#c0392b",
            width=100,
            command=self.clear_all
        )
        self.btn_clear.pack(side="left")

        # Copy JS Output Button
        self.btn_copy = ctk.CTkButton(
            self.toolbar_frame, 
            text="📋 Salin JavaScript", 
            width=130,
            command=self.copy_output
        )
        self.btn_copy.pack(side="right", padx=(10, 0))

        # Save File Button
        self.btn_save = ctk.CTkButton(
            self.toolbar_frame, 
            text="💾 Simpan .js", 
            fg_color="#27ae60", 
            hover_color="#219150",
            width=110,
            command=self.save_to_file
        )
        self.btn_save.pack(side="right")

        # ------------------- EDITOR SECTION -------------------
        # Input Section (Kiri)
        self.input_frame = ctk.CTkFrame(self)
        self.input_frame.grid(row=2, column=0, padx=(20, 10), pady=10, sticky="nsew")
        self.input_frame.grid_rowconfigure(1, weight=1)
        self.input_frame.grid_columnconfigure(0, weight=1)

        self.input_label = ctk.CTkLabel(
            self.input_frame, 
            text="Input UML Kode:", 
            font=("Segoe UI", 13, "bold")
        )
        self.input_label.grid(row=0, column=0, sticky="w", padx=10, pady=5)

        self.txt_input = ctk.CTkTextbox(self.input_frame, font=("Consolas", 13), wrap="none")
        self.txt_input.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")

        # Output Section (Kanan)
        self.output_frame = ctk.CTkFrame(self)
        self.output_frame.grid(row=2, column=1, padx=(10, 20), pady=10, sticky="nsew")
        self.output_frame.grid_rowconfigure(1, weight=1)
        self.output_frame.grid_columnconfigure(0, weight=1)

        self.output_label = ctk.CTkLabel(
            self.output_frame, 
            text="Hasil Kode JavaScript:", 
            font=("Segoe UI", 13, "bold")
        )
        self.output_label.grid(row=0, column=0, sticky="w", padx=10, pady=5)

        self.txt_output = ctk.CTkTextbox(self.output_frame, font=("Consolas", 13), wrap="none")
        self.txt_output.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")

        # ------------------- COMPILE BUTTON -------------------
        self.btn_compile = ctk.CTkButton(
            self, 
            text="🚀 Compile ke JavaScript", 
            font=("Segoe UI", 14, "bold"),
            height=40,
            command=self.on_compile
        )
        self.btn_compile.grid(row=3, column=0, columnspan=2, padx=20, pady=10, sticky="ew")

        # ------------------- STATUS BAR -------------------
        self.lbl_status = ctk.CTkLabel(
            self, 
            text="Siap. Silakan masukkan kode UML Anda.", 
            font=("Segoe UI", 11),
            anchor="w",
            text_color="gray"
        )
        self.lbl_status.grid(row=4, column=0, columnspan=2, padx=20, pady=(0, 10), sticky="ew")

    # ------------------- EVENT HANDLERS -------------------
    def on_compile(self):
        input_text = self.txt_input.get("0.0", "end")
        success, result = compile_uml_to_js(input_text)

        self.txt_output.delete("0.0", "end")
        self.txt_output.insert("0.0", result)

        if success:
            self.set_status("✅ Berhasil dicompile ke JavaScript!", color="#2ecc71")
        else:
            self.set_status(f"❌ {result}", color="#e74c3c")

    def load_sample(self, choice):
        if choice in SAMPLES:
            self.txt_input.delete("0.0", "end")
            self.txt_input.insert("0.0", SAMPLES[choice])
            self.set_status(f"Memuat contoh format {choice}.", color="gray")
            self.sample_option.set("Muat Contoh Input...")

    def clear_all(self):
        self.txt_input.delete("0.0", "end")
        self.txt_output.delete("0.0", "end")
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
            filetypes=[("JavaScript Files", "*.js"), ("All Files", "*.*")]
        )
        if file_path:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(output_text)
            self.set_status(f"💾 File berhasil disimpan di: {file_path}", color="#2ecc71")

    def set_status(self, message, color="gray"):
        self.lbl_status.configure(text=message, text_color=color)


if __name__ == "__main__":
    app = UMLCompilerApp()
    app.mainloop()