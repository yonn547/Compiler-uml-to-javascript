# xtUML → JavaScript Compiler

Compiler model **xtUML (Executable UML)** menjadi JavaScript ES2020. Pipeline:

```
source → parser → IR kanonik → validator → generator → JS bundle / project ESM + runtime
```

## Fitur yang sudah ada

- **4 format input**: DSL xtUML berbasis teks, XML xtUML terstruktur, JSON/IR kanonik, dan PlantUML object diagram (kompatibel dengan input lama).
- **IR kanonik** berbentuk JSON (`--emit-ir` / tombol *Simpan IR*) yang bisa di-roundtrip.
- **Parser berbasis lexer** dengan posisi baris/kolom (bukan regex), termasuk escape string dan komentar.
- **Validasi semantik**: duplikat nama, referensi class/instance/association, multiplicity, state machine (initial state, event, transisi, state unreachable), ekspresi action language.
- **Generator JavaScript**: class ES6,runtime association + navigasi role, state machine engine + event queue sederhana, action language (`log`, `let`, assignment, `if`, `while`, `create`, `delete`, `link`, `unlink`, `generate`, `return`).
- **Dua mode output**:
  - bundle satu file `.js` (bisa dipakai di Node via `require` atau browser via `window.UmlModel`);
  - project multi-file ESM (`package.json`, `src/runtime.js`, `src/classes/*.js`, `src/model.js`, `src/index.js`).
- **GUI** CustomTkinter: editor, diagnostics, pemilih format/target, contoh model, salin/simpan JS, simpan IR.
- **Class diagram** di panel hasil (tab *Class Diagram*): class + atribut + operasi + state machine, datatype, asosiasi dengan multiplicity, dan generalisasi (`extends`) digambar langsung di canvas. Tombol *Salin PUML* / *Simpan .puml* tersedia di tab tersebut.
- **Highlight error/peringatan langsung di editor** (baris bermasalah diberi warna; klik 2× diagnostics untuk lompat ke baris).
- **Simulator interaktif** di tab *Simulator*: pilih instance, kirim event dengan payload JSON, lihat state/atribut/association dan log `console.log`, reset state. Simulator dijalankan sebagai proses Node yang tetap hidup antar-perintah.
- **CLI** `python -m xtuml_compiler` dengan perintah `compile`, `check`, `formats`.
- **Test otomatis** dengan `unittest` (termasuk eksekusi hasil compile di Node).

## Instalasi

```bash
python -m venv myenv
source myenv/bin/activate     # Windows: myenv\Scripts\activate
pip install -r requirements.txt
```

Compiler inti hanya memakai standard library Python. `customtkinter` hanya diperlukan untuk GUI.

## GUI

```bash
python app.py
```

Jika `myenv` bawaan repo tidak aktif di mesin Anda (venv dibuat di path lain), jalankan dengan:

```bash
PYTHONPATH=myenv/lib/python3.12/site-packages python3 app.py
```

Pilih *Muat Contoh Input... → xtUML DSL*, lalu tekan **Compile** (atau `Ctrl+Enter`). Panel kanan atas memiliki tab **JavaScript** dan **Class Diagram**; panel bawah menampilkan error/warning beserta nomor baris. Diagram bisa disalin sebagai PlantUML atau disimpan ke file `.puml`.

## CLI

```bash
# Cek model tanpa generate kode
python -m xtuml_compiler check examples/shop.xtuml

# Bundle satu file
python -m xtuml_compiler compile examples/shop.xtuml -o dist/shop.js

# Project ESM + simpan IR kanonik
python -m xtuml_compiler compile examples/shop.xtuml --project -o dist/shop_js \
  --ir dist/shop.ir.json

# Format yang didukung
python -m xtuml_compiler formats

# Ekspor class diagram (PlantUML atau Mermaid sesuai ekstensi)
python -m xtuml_compiler compile examples/shop.xtuml --diagram dist/shop.puml
python -m xtuml_compiler compile examples/shop.xtuml --diagram dist/shop.mmd
```

Opsi penting: `--format {auto,dsl,json,xml,plantuml}`, `--target {node,browser}`, `--project`, `--ir`, `--diagram`, `--diagram-format {auto,plantuml,mermaid}`, `--quiet`.

## Contoh pemakaian hasil compile

```js
const model = require("./dist/shop.js");
const customer = model.instances.c1;

console.log(customer.label());          // Customer Alice
console.log(customer.orders.length);    // 1 (navigasi association)
customer.generate("activate");         // jalankan transisi state machine
console.log(customer.state);            // active
```

Untuk project ESM:

```js
import { UmlModel } from "./dist/shop_js/src/index.js";
```

## Struktur kode

```
app.py                         GUI CustomTkinter
xtuml_compiler/
  diagnostics.py               error/warning/info + lokasi
  diagram.py                   class diagram: layout + PlantUML/Mermaid
  utils.py                     identifier JS, multiplicity, literal
  ir/model.py                  dataclass IR + serialisasi JSON
  validator.py                 analisis semantik
  frontend/
    dsl/{lexer,parser}.py      parser DSL xtUML
    json/parser.py             JSON/IR + object diagram lama
    xml/parser.py              XML xtUML + XML lama
    plantuml/parser.py         PlantUML object diagram
    common.py                  adapter format lama → IR
  backend/js/
    expression.py              action language → ekspresi JS
    emitter.py                 generator bundle/project
    runtime.js                 runtime (registry, association, state machine, event bus)
  cli.py                       argparse CLI
  simulator.py                 wrapper proses Node untuk simulasi
  simulator_driver.js          driver JSON stdin/stdout untuk bundle hasil compile
examples/shop.xtuml            contoh lengkap
tests/test_compiler.py         unittest + integrasi Node
docs/FORMAT.md                 referensi sintaks DSL/XML
```

## Batasan saat ini

- Action language masih **subset**; belum mendukung Alf/OAL penuh.
- State machine masih **flat** (belum hierarkis/konkuren), belum ada deferred event & timer.
- Event bersifat sinkron via `generate()`; `EventBus` tersedia tetapi belum dipakai generator.
- Simulator GUI memakai bundle satu file (project ESM belum bisa disimulasikan langsung dari GUI).
- Tidak ada source map, inkremental compile, atau LSP/VS Code extension (rencana lanjutan).

Lihat `docs/FORMAT.md` untuk sintaks lengkap.
