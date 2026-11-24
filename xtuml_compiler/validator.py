"""Validasi semantik model xtUML sebelum generator JS dijalankan."""

from __future__ import annotations

from collections import defaultdict, deque

from .backend.js.expression import check_expression
from .diagnostics import Diagnostics
from .ir.model import Model, Statement
from .utils import is_js_identifier, js_identifier, parse_multiplicity


def _check_name(kind: str, name: str, line: int, diagnostics: Diagnostics) -> None:
    if not name:
        diagnostics.error(f"{kind} tidak boleh kosong", line=line)
        return
    js_name = js_identifier(name)
    if js_name != name:
        diagnostics.warning(
            f"{kind} '{name}' akan ditulis sebagai '{js_name}' di JavaScript",
            line=line,
        )
    elif not is_js_identifier(name):
        diagnostics.warning(f"{kind} '{name}' adalah kata kunci JavaScript", line=line)


def _check_statements(statements: list[Statement], diagnostics: Diagnostics, line: int = 0) -> None:
    expression_kinds = {"log", "let", "return", "assign", "expr", "delete", "if", "while"}
    for statement in statements:
        current_line = statement.line or line
        if statement.kind in expression_kinds and statement.expression:
            error = check_expression(statement.expression)
            if error:
                diagnostics.error(f"Ekspresi tidak valid: {error}", line=current_line)
        if statement.kind in ("link", "unlink", "generate") and statement.target:
            error = check_expression(statement.target)
            if error:
                diagnostics.error(f"Ekspresi objek tidak valid: {error}", line=current_line)
        if statement.kind == "generate" and statement.payload:
            error = check_expression(statement.payload)
            if error:
                diagnostics.error(f"Payload event tidak valid: {error}", line=current_line)
        _check_statements(statement.body, diagnostics, current_line)
        _check_statements(statement.orelse, diagnostics, current_line)


def validate(model: Model, diagnostics: Diagnostics | None = None) -> Diagnostics:
    """Validasi model. Diagnostics yang diberikan akan diisi (bukan diganti)."""
    diagnostics = diagnostics or Diagnostics()
    _check_name("Domain", model.name, 0, diagnostics)

    class_names: set[str] = set()
    for class_def in model.classes:
        _check_name("Class", class_def.name, class_def.line, diagnostics)
        if class_def.name in class_names:
            diagnostics.error(f"Class '{class_def.name}' duplikat", line=class_def.line)
        class_names.add(class_def.name)
        if class_def.base and class_def.base not in {item.name for item in model.classes}:
            diagnostics.warning(
                f"Class induk '{class_def.base}' tidak ditemukan", line=class_def.line
            )

        attr_names: set[str] = set()
        for attribute in class_def.attributes:
            _check_name("Attribute", attribute.name, attribute.line, diagnostics)
            if attribute.name in attr_names:
                diagnostics.error(
                    f"Attribute '{attribute.name}' duplikat di class '{class_def.name}'",
                    line=attribute.line,
                )
            attr_names.add(attribute.name)
            if attribute.default:
                error = check_expression(attribute.default)
                if error:
                    diagnostics.error(f"Default attribute tidak valid: {error}", line=attribute.line)

        operation_names: set[str] = set()
        for operation in class_def.operations:
            _check_name("Operation", operation.name, operation.line, diagnostics)
            if operation.name in operation_names:
                diagnostics.error(
                    f"Operation '{operation.name}' duplikat di class '{class_def.name}'",
                    line=operation.line,
                )
            operation_names.add(operation.name)
            param_names: set[str] = set()
            for param in operation.params:
                _check_name("Parameter", param.name, operation.line, diagnostics)
                if param.name in param_names:
                    diagnostics.error(
                        f"Parameter '{param.name}' duplikat di operation '{operation.name}'",
                        line=operation.line,
                    )
                param_names.add(param.name)
            _check_statements(operation.body, diagnostics, operation.line)

        sm_names: set[str] = set()
        for machine in class_def.state_machines:
            _check_name("State machine", machine.name, machine.line, diagnostics)
            if machine.name in sm_names:
                diagnostics.error(
                    f"State machine '{machine.name}' duplikat di class '{class_def.name}'",
                    line=machine.line,
                )
            sm_names.add(machine.name)
            _validate_state_machine(machine, class_def.name, diagnostics)

    _validate_associations(model, diagnostics)
    _validate_instances(model, diagnostics)
    _validate_links(model, diagnostics)
    return diagnostics


def _validate_state_machine(machine, class_name: str, diagnostics: Diagnostics) -> None:
    state_names = [state.name for state in machine.states]
    if len(set(state_names)) != len(state_names):
        diagnostics.error(
            f"State duplikat di state machine '{machine.name}' ({class_name})",
            line=machine.line,
        )
    initials = [state for state in machine.states if state.initial]
    if machine.states and len(initials) != 1:
        if not initials:
            diagnostics.warning(
                f"State machine '{machine.name}' tidak punya state initial; "
                f"'{machine.states[0].name}' dipakai sebagai default",
                line=machine.line,
            )
        else:
            diagnostics.error(
                f"State machine '{machine.name}' memiliki {len(initials)} state initial",
                line=machine.line,
            )

    event_names = [event.name for event in machine.events]
    if len(set(event_names)) != len(event_names):
        diagnostics.error(f"Event duplikat di state machine '{machine.name}'", line=machine.line)
    for event in machine.events:
        _check_name("Event", event.name, event.line, diagnostics)

    known_states = set(state_names)
    known_events = set(event_names)
    adjacency: dict[str, list[str]] = defaultdict(list)
    finals = {state.name for state in machine.states if state.final}

    for transition in machine.transitions:
        if transition.source not in known_states:
            diagnostics.error(
                f"Transisi dari state '{transition.source}' yang tidak ditemukan",
                line=transition.line,
            )
        if transition.target not in known_states:
            diagnostics.error(
                f"Transisi ke state '{transition.target}' yang tidak ditemukan",
                line=transition.line,
            )
        if transition.event not in known_events:
            diagnostics.error(
                f"Transisi memakai event '{transition.event}' yang tidak didefinisikan",
                line=transition.line,
            )
        if transition.source in finals:
            diagnostics.error(
                f"Transisi keluar dari state final '{transition.source}'",
                line=transition.line,
            )
        if transition.guard:
            error = check_expression(transition.guard)
            if error:
                diagnostics.error(f"Guard tidak valid: {error}", line=transition.line)
        _check_statements(transition.body, diagnostics, transition.line)
        adjacency[transition.source].append(transition.target)

    for state in machine.states:
        _check_statements(state.entry, diagnostics, state.line)
        _check_statements(state.exit, diagnostics, state.line)

    if machine.states:
        initial = initials[0].name if len(initials) == 1 else machine.states[0].name
        visited = {initial}
        queue = deque([initial])
        while queue:
            current = queue.popleft()
            for next_state in adjacency.get(current, []):
                if next_state not in visited:
                    visited.add(next_state)
                    queue.append(next_state)
        unreachable = [name for name in state_names if name not in visited]
        if unreachable:
            diagnostics.warning(
                f"State tidak dapat dicapai dari '{initial}': {', '.join(unreachable)}",
                line=machine.line,
            )


def _validate_associations(model: Model, diagnostics: Diagnostics) -> None:
    names: set[str] = set()
    class_names = {item.name for item in model.classes}
    for association in model.associations:
        _check_name("Association", association.name, association.line, diagnostics)
        if association.name in names:
            diagnostics.error(f"Association '{association.name}' duplikat", line=association.line)
        names.add(association.name)
        for end in (association.end_a, association.end_b):
            if end.class_name not in class_names:
                diagnostics.error(
                    f"Association '{association.name}' merujuk class '{end.class_name}' "
                    "yang tidak ditemukan",
                    line=end.line or association.line,
                )
            _check_name("Role", end.role, end.line or association.line, diagnostics)
            if parse_multiplicity(end.multiplicity) is None:
                diagnostics.error(
                    f"Multiplicity '{end.multiplicity}' tidak valid pada role '{end.role}'",
                    line=end.line or association.line,
                )
        if association.end_a.role == association.end_b.role and (
            association.end_a.class_name == association.end_b.class_name
        ):
            diagnostics.error(
                f"Kedua ujung association '{association.name}' memakai role '{association.end_a.role}'",
                line=association.line,
            )


def _validate_instances(model: Model, diagnostics: Diagnostics) -> None:
    names: set[str] = set()
    class_map = {item.name: item for item in model.classes}
    for instance in model.instances:
        _check_name("Instance", instance.name, instance.line, diagnostics)
        if instance.name in names:
            diagnostics.error(f"Instance '{instance.name}' duplikat", line=instance.line)
        names.add(instance.name)
        class_def = class_map.get(instance.class_name)
        if class_def is None:
            diagnostics.error(
                f"Instance '{instance.name}' memakai class '{instance.class_name}' "
                "yang tidak ditemukan",
                line=instance.line,
            )
            continue
        known = {attribute.name for attribute in class_def.attributes}
        for key, value in instance.values.items():
            if key not in known:
                diagnostics.warning(
                    f"Instance '{instance.name}' memiliki atribut '{key}' "
                    f"yang tidak didefinisikan di class '{instance.class_name}'",
                    line=instance.line,
                )
            error = check_expression(str(value))
            if error:
                diagnostics.error(
                    f"Nilai atribut '{key}' tidak valid: {error}", line=instance.line
                )


def _validate_links(model: Model, diagnostics: Diagnostics) -> None:
    association_map = {item.name: item for item in model.associations}
    instance_map = {item.name: item for item in model.instances}
    counts: dict[tuple[str, int, str], int] = defaultdict(int)
    seen_pairs: set[tuple[str, str, str]] = set()

    for link in model.links:
        association = association_map.get(link.association)
        if association is None:
            diagnostics.error(
                f"Link memakai association '{link.association}' yang tidak ditemukan",
                line=link.line,
            )
            continue
        source = instance_map.get(link.source)
        target = instance_map.get(link.target)
        if source is None:
            diagnostics.error(f"Link merujuk instance '{link.source}' yang tidak ada", line=link.line)
            continue
        if target is None:
            diagnostics.error(f"Link merujuk instance '{link.target}' yang tidak ada", line=link.line)
            continue

        if (
            source.class_name == association.end_a.class_name
            and target.class_name == association.end_b.class_name
        ):
            first, second = source, target
        elif (
            source.class_name == association.end_b.class_name
            and target.class_name == association.end_a.class_name
        ):
            first, second = target, source
        else:
            diagnostics.error(
                f"Link {link.source} -> {link.target} tidak cocok dengan ujung "
                f"association '{link.association}'",
                line=link.line,
            )
            continue

        pair = (link.association, first.name, second.name)
        if pair in seen_pairs:
            diagnostics.warning(f"Link duplikat pada association '{link.association}'", line=link.line)
        seen_pairs.add(pair)

        counts[(link.association, 0, first.name)] += 1
        counts[(link.association, 1, second.name)] += 1

    for association in model.associations:
        for index, end in enumerate((association.end_a, association.end_b)):
            parsed = parse_multiplicity(end.multiplicity)
            if parsed is None:
                continue
            maximum = parsed[1]
            for (assoc_name, side, instance_name), total in counts.items():
                if assoc_name != association.name or side != index:
                    continue
                if total > maximum:
                    diagnostics.error(
                        f"Instance '{instance_name}' memiliki {total} link pada role "
                        f"'{end.role}', maksimal {int(maximum) if maximum != float('inf') else '∞'}",
                        line=association.line,
                    )
