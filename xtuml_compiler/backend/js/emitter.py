"""Generator JavaScript (ES2020+) dari IR xtUML."""

from __future__ import annotations

import json
import re
from pathlib import Path

from ...ir.model import Association, ClassDef, Model, Statement, StateMachine
from ...utils import js_identifier, literal_to_expr, parse_literal, slugify
from .expression import ExpressionError, translate_expression


RUNTIME_PATH = Path(__file__).with_name("runtime.js")


class CodegenError(ValueError):
    pass


def runtime_source() -> str:
    return RUNTIME_PATH.read_text(encoding="utf-8")


def _bundle_runtime() -> str:
    lines = []
    for line in runtime_source().splitlines():
        lines.append(re.sub(r"^export\s+", "", line))
    return "\n".join(lines)


def class_name(name: str) -> str:
    return js_identifier(name, "GeneratedClass")


def _sm_name(class_def: ClassDef, machine: StateMachine) -> str:
    return f"sm_{class_name(class_def.name)}_{js_identifier(machine.name)}"


def _assoc_name(association: Association) -> str:
    return f"assoc_{js_identifier(association.name)}"


def _expr(text: str) -> str:
    try:
        return translate_expression(text)
    except ExpressionError as exc:
        raise CodegenError(str(exc)) from exc


def _event_literal(text: str) -> str:
    raw = str(text or "").strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ('"', "'"):
        raw = parse_literal(raw)
    return json.dumps(str(raw), ensure_ascii=False)


def _function(body: str, indent: int) -> str:
    lines = body.splitlines() if body.strip() else []
    if not lines:
        return "function (payload) {}"
    pad = " " * indent
    inner = "\n".join(" " * (indent + 2) + line for line in lines)
    return f"function (payload) {{\n{inner}\n{pad}}}"


def emit_statements(statements: list[Statement], indent: str = "  ") -> str:
    lines: list[str] = []
    for statement in statements:
        kind = statement.kind
        if kind == "log":
            lines.append(f"{indent}console.log({_expr(statement.expression)});")
        elif kind == "let":
            lines.append(
                f"{indent}let {js_identifier(statement.target)} = {_expr(statement.expression)};"
            )
        elif kind == "assign":
            lines.append(f"{indent}{_expr(statement.target)} = {_expr(statement.expression)};")
        elif kind == "return":
            lines.append(f"{indent}return {_expr(statement.expression)};")
        elif kind == "create":
            construction = f"new {class_name(statement.class_name)}()"
            if statement.target:
                lines.append(f"{indent}let {js_identifier(statement.target)} = {construction};")
            else:
                lines.append(f"{indent}{construction};")
        elif kind == "delete":
            lines.append(f"{indent}UmlObject.registry.remove({_expr(statement.expression)});")
        elif kind in ("link", "unlink"):
            lines.append(
                f"{indent}{_assoc_name(Association(statement.class_name, None, None))}."
                f"{kind}({_expr(statement.expression)}, {_expr(statement.target)});"
            )
        elif kind == "generate":
            payload = _expr(statement.payload) if statement.payload else ""
            arguments = _event_literal(statement.expression)
            if payload:
                arguments += f", {payload}"
            lines.append(f"{indent}{_expr(statement.target)}.generate({arguments});")
        elif kind == "if":
            lines.append(f"{indent}if ({_expr(statement.expression)}) {{")
            lines.append(emit_statements(statement.body, indent + "  "))
            if statement.orelse:
                lines.append(f"{indent}}} else {{")
                lines.append(emit_statements(statement.orelse, indent + "  "))
            lines.append(f"{indent}}}")
        elif kind == "while":
            lines.append(f"{indent}while ({_expr(statement.expression)}) {{")
            lines.append(emit_statements(statement.body, indent + "  "))
            lines.append(f"{indent}}}")
        elif kind == "expr":
            lines.append(f"{indent}{_expr(statement.expression)};")
        else:
            raise CodegenError(f"Jenis statement tidak dikenal: {kind}")
    return "\n".join(line for line in lines if line != "")


def emit_state_machine(class_def: ClassDef, machine: StateMachine) -> str:
    name = _sm_name(class_def, machine)
    lines = [
        f"const {name} = new StateMachine({{",
        f"  name: {json.dumps(machine.name)},",
        f"  owner: {json.dumps(class_def.name)},",
        f"  initial: {json.dumps(machine.initial_state)},",
        "  states: {",
    ]
    state_lines: list[str] = []
    for state in machine.states:
        entry = _function(emit_statements(state.entry), 6)
        exit_fn = _function(emit_statements(state.exit), 6)
        state_lines.append(
            f"    {json.dumps(state.name)}: {{\n"
            f"      initial: {'true' if state.initial else 'false'},\n"
            f"      final: {'true' if state.final else 'false'},\n"
            f"      entry: {entry},\n"
            f"      exit: {exit_fn}\n"
            f"    }}"
        )
    lines.append(",\n".join(state_lines))
    lines.append("  },")
    lines.append(
        "  events: [" + ", ".join(json.dumps(event.name) for event in machine.events) + "],"
    )
    lines.append("  transitions: [")
    transition_lines: list[str] = []
    for transition in machine.transitions:
        block = [
            "    {",
            f"      from: {json.dumps(transition.source)},",
            f"      to: {json.dumps(transition.target)},",
            f"      event: {json.dumps(transition.event)},",
        ]
        if transition.guard:
            guard = _function(f"return {_expr(transition.guard)};", 6)
            block.append(f"      guard: {guard},")
        action = _function(emit_statements(transition.body), 6)
        block.append(f"      action: {action}")
        block.append("    }")
        transition_lines.append("\n".join(block))
    lines.append(",\n".join(transition_lines))
    lines.append("  ]")
    lines.append("});")
    return "\n".join(lines)


def emit_class(model: Model, class_def: ClassDef) -> str:
    name = class_name(class_def.name)
    base = "UmlObject"
    if class_def.base and model.find_class(class_def.base):
        base = class_name(class_def.base)
    lines = [f"/** @class {class_def.name} */", f"class {name} extends {base} {{"]
    defaults = [f"_class: {json.dumps(class_def.name, ensure_ascii=False)}"]
    for attribute in class_def.attributes:
        value = _expr(attribute.default) if attribute.default else "null"
        defaults.append(f"{js_identifier(attribute.name)}: {value}")
    lines.append("  constructor(attributes = {}) {")
    lines.append(f"    super({{ {', '.join(defaults)}, ...attributes }});")
    lines.append("  }")
    for operation in class_def.operations:
        params = ", ".join(js_identifier(param.name) for param in operation.params)
        lines.append("")
        lines.append(f"  /** @returns {{{operation.return_type}}} */")
        lines.append(f"  {js_identifier(operation.name)}({params}) {{")
        body = emit_statements(operation.body, "    ")
        if body:
            lines.append(body)
        lines.append("  }")
    lines.append("}")
    return "\n".join(lines)


def emit_association(association: Association) -> str:
    def end_block(end, role: str) -> str:
        return (
            "{ "
            f"className: {json.dumps(end.class_name)}, "
            f"role: {json.dumps(role)}, "
            f"multiplicity: {json.dumps(str(end.multiplicity))} "
            "}"
        )

    role_a = js_identifier(association.end_a.role)
    role_b = js_identifier(association.end_b.role)
    return (
        f"const {_assoc_name(association)} = new Association("
        f"{json.dumps(association.name)}, "
        f"{end_block(association.end_a, role_a)}, "
        f"{end_block(association.end_b, role_b)});"
    )


def emit_instance(model: Model, instance) -> str:
    values = []
    class_def = model.find_class(instance.class_name)
    for key, value in instance.values.items():
        values.append(f"{js_identifier(key)}: {_expr(str(value))}")
    if class_def is None:
        values.insert(0, f"_class: {json.dumps(instance.class_name)}")
    return (
        f"const {js_identifier(instance.name)} = new {class_name(instance.class_name)}("
        f"{{ {', '.join(values)} }});"
    )


def _export_object(model: Model, esm: bool = False, include_machines: bool = True) -> str:
    classes = ", ".join(
        f"{json.dumps(class_def.name)}: {class_name(class_def.name)}"
        for class_def in model.classes
    )
    associations = ", ".join(
        f"{json.dumps(item.name)}: {_assoc_name(item)}" for item in model.associations
    )
    instances = ", ".join(
        f"{json.dumps(item.name)}: {js_identifier(item.name)}" for item in model.instances
    )
    machines = ", ".join(
        f"{json.dumps(class_def.name)}: {{ "
        + ", ".join(
            f"{json.dumps(machine.name)}: {_sm_name(class_def, machine)}"
            for machine in class_def.state_machines
        )
        + " }"
        for class_def in model.classes
        if class_def.state_machines
    )
    head = "const UmlModel = {"
    if esm:
        tail = "export { UmlModel };"
    else:
        tail = (
            'if (typeof module !== "undefined" && module.exports) module.exports = UmlModel;\n'
            'if (typeof window !== "undefined") window.UmlModel = UmlModel;'
        )
    return (
        f"{head}\n"
        f"  domain: {json.dumps(model.name, ensure_ascii=False)},\n"
        f"  classes: {{ {classes} }},\n"
        f"  associations: {{ {associations} }},\n"
        f"  instances: {{ {instances} }}"
        + (f",\n  stateMachines: {{ {machines} }}\n" if include_machines else "\n")
        + f"}};\n{tail}"
    )


def generate_bundle(model: Model, target: str = "node") -> str:
    """Hasil compile satu file JavaScript yang bisa langsung dijalankan."""
    sections = [
        "// ============================================================",
        f"// Generated by xtUML Compiler from {model.source_type}",
        f"// Domain: {model.name} | target: {target}",
        "// ============================================================",
        "",
        _bundle_runtime(),
        "",
    ]
    declarations: list[str] = []
    for class_def in model.classes:
        for machine in class_def.state_machines:
            declarations.append(emit_state_machine(class_def, machine))
    if declarations:
        sections.extend(["// ---- State machines ----", "\n\n".join(declarations), ""])

    if model.classes:
        sections.append("// ---- Classes ----")
        sections.extend(emit_class(model, class_def) for class_def in model.classes)
        sections.append("")

    installs: list[str] = []
    for class_def in model.classes:
        for machine in class_def.state_machines:
            installs.append(f"{_sm_name(class_def, machine)}.install({class_name(class_def.name)});")
    if installs:
        sections.extend(["// ---- Wire state machines ----", *installs, ""])

    if model.associations:
        sections.append("// ---- Associations ----")
        sections.extend(emit_association(item) for item in model.associations)
        sections.extend(
            f"{_assoc_name(item)}.install("
            f"{class_name(item.end_a.class_name)}, {class_name(item.end_b.class_name)});"
            for item in model.associations
        )
        sections.append("")

    if model.instances:
        sections.append("// ---- Instances ----")
        sections.extend(emit_instance(model, instance) for instance in model.instances)
        sections.append("")

    if model.links:
        sections.append("// ---- Links ----")
        sections.extend(
            f"{_assoc_name(Association(link.association, None, None))}.link("
            f"{js_identifier(link.source)}, {js_identifier(link.target)});"
            for link in model.links
        )
        sections.append("")

    sections.extend(["// ---- Exports ----", _export_object(model), ""])
    return "\n".join(sections)


def generate_project(model: Model, target: str = "node") -> dict[str, str]:
    """Hasil compile sebagai beberapa modul ES."""
    files: dict[str, str] = {
        "package.json": json.dumps(
            {
                "name": slugify(model.name),
                "version": "0.1.0",
                "type": "module",
                "main": "src/index.js",
                "scripts": {"check": "node --check src/index.js"},
            },
            indent=2,
        )
        + "\n",
        "src/runtime.js": runtime_source(),
        "README.md": (
            f"# {model.name}\n\n"
            "Kode ini dihasilkan oleh xtUML Compiler.\n\n"
            "```bash\nnode --check src/index.js\nnode -e \"import('./src/index.js')\"\n```\n"
        ),
    }

    class_lines: dict[str, list[str]] = {}
    for class_def in model.classes:
        imports = ["import { UmlObject, StateMachine } from \"../runtime.js\";"]
        if class_def.base and model.find_class(class_def.base):
            imports.append(f'import {{ {class_name(class_def.base)} }} from "./{class_name(class_def.base)}.js";')
        body: list[str] = []
        for machine in class_def.state_machines:
            body.append(emit_state_machine(class_def, machine))
            body.append("")
        body.append(emit_class(model, class_def))
        for machine in class_def.state_machines:
            body.append(f"{_sm_name(class_def, machine)}.install({class_name(class_def.name)});")
        body.append("")
        body.append(
            "export const stateMachines = { "
            + ", ".join(
                f"{json.dumps(machine.name)}: {_sm_name(class_def, machine)}"
                for machine in class_def.state_machines
            )
            + " };"
        )
        body.append(f"export {{ {class_name(class_def.name)} }};")
        class_lines[class_name(class_def.name)] = imports + ["", *body]

    for name, lines in class_lines.items():
        files[f"src/classes/{name}.js"] = "\n".join(lines) + "\n"

    model_lines = [
        'import { Association } from "./runtime.js";',
    ]
    for class_def in model.classes:
        model_lines.append(
            f'import {{ {class_name(class_def.name)} }} from "./classes/{class_name(class_def.name)}.js";'
        )
    model_lines.append("")
    for association in model.associations:
        model_lines.append(emit_association(association))
    if model.associations:
        model_lines.append("")
        for association in model.associations:
            model_lines.append(
                f"{_assoc_name(association)}.install("
                f"{class_name(association.end_a.class_name)}, "
                f"{class_name(association.end_b.class_name)});"
            )
        model_lines.append("")
    if model.instances:
        model_lines.append("// ---- Instances ----")
        model_lines.extend(emit_instance(model, item) for item in model.instances)
        model_lines.append("")
    if model.links:
        model_lines.append("// ---- Links ----")
        model_lines.extend(
            f"{_assoc_name(Association(link.association, None, None))}.link("
            f"{js_identifier(link.source)}, {js_identifier(link.target)});"
            for link in model.links
        )
        model_lines.append("")
    model_lines.append(_export_object(model, esm=True, include_machines=False))
    model_lines.append("")
    files["src/model.js"] = "\n".join(model_lines)

    exports = ['export { UmlModel } from "./model.js";', 'export * from "./runtime.js";']
    files["src/index.js"] = "\n".join(exports) + "\n"
    return files
