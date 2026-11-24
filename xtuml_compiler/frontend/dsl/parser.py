"""Parser untuk DSL xtUML teks.

Contoh sintaks::

    domain Shop {
      class Order {
        attribute total : real
        state machine lifecycle {
          event confirm
          state pending initial { entry: log("baru") }
          state paid final
          transition pending -> paid on confirm when total > 0 { log("lunas") }
        }
        operation label() : string { return "Order" }
      }
      association userOrder between User.orders [0..*] and Order.user [1]
      instance o1 of Order { total = 100 }
      link c1 to o1 via userOrder
    }
"""

from __future__ import annotations

import re

from ...diagnostics import Diagnostics
from ...ir.model import (
    AssocEnd,
    Association,
    AttributeDef,
    ClassDef,
    DataType,
    EventDef,
    Instance,
    Link,
    Model,
    Operation,
    Parameter,
    State,
    StateMachine,
    Statement,
    Transition,
)
from ...utils import literal_to_expr, parse_literal
from .lexer import Lexer, Token


class ParseAbort(Exception):
    """Dipakai untuk menghentikan satu rule saat error struktural."""


class DSLParser:
    def __init__(self, text: str, source: str = "<input>", diagnostics: Diagnostics | None = None):
        self.diagnostics = diagnostics or Diagnostics()
        self.tokens = Lexer(text, source, self.diagnostics).tokenize()
        self.index = 0
        self.source = source

    # ------------------------------------------------------------------ utils
    def current(self) -> Token:
        return self.tokens[self.index]

    def advance(self) -> Token:
        token = self.current()
        if token.type != "EOF":
            self.index += 1
        return token

    def error(self, message: str, token: Token | None = None) -> None:
        token = token or self.current()
        self.diagnostics.error(message, self.source, token.line, token.column)

    def skip_blank(self) -> None:
        while self.current().type == "NEWLINE" or (
            self.current().type == "OP" and self.current().value == ";"
        ):
            self.advance()

    def expect(self, value: str) -> Token:
        if self.current().value == value:
            return self.advance()
        self.error(f"Diharapkan '{value}', ditemukan '{self.current().value or 'EOF'}'")
        raise ParseAbort()

    def expect_ident(self) -> Token:
        if self.current().type == "IDENT":
            return self.advance()
        self.error(f"Diharapkan identifier, ditemukan '{self.current().value or 'EOF'}'")
        raise ParseAbort()

    def take_until(self, stops: set[str]) -> list[Token]:
        tokens: list[Token] = []
        while True:
            token = self.current()
            if token.type in ("NEWLINE", "EOF") or token.value in stops or token.value == "}":
                break
            tokens.append(self.advance())
        return tokens

    def take_line(self) -> list[Token]:
        return self.take_until(set())

    def collect_balanced(self, opening: str, closing: str) -> list[Token]:
        self.expect(opening)
        depth = 1
        collected: list[Token] = []
        while self.current().type != "EOF":
            token = self.current()
            if token.value == opening:
                depth += 1
            elif token.value == closing:
                depth -= 1
                if depth == 0:
                    self.advance()
                    return collected
            collected.append(self.advance())
        self.error(f"Kurung '{opening}' tidak ditutup")
        raise ParseAbort()

    def text(self, tokens: list[Token]) -> str:
        """Gabungkan token menjadi teks, menjaga isi string tetap utuh."""
        strings: list[str] = []
        values: list[str] = []
        for token in tokens:
            if token.type == "STRING":
                values.append(f"__STR{len(strings)}__")
                strings.append(token.value)
            else:
                values.append(token.value)
        result = " ".join(values)
        result = re.sub(r"\s+", " ", result)
        result = re.sub(r"\s*\.\s*", ".", result)
        result = re.sub(r"\s*,\s*", ", ", result)
        result = re.sub(r"\s*\(\s*", "(", result)
        result = re.sub(r"\s*\)\s*", ")", result)
        result = re.sub(r"\s*\[\s*", "[", result)
        result = re.sub(r"\s*\]\s*", "]", result)
        for index, value in enumerate(strings):
            result = result.replace(f"__STR{index}__", value)
        return result.strip()

    def skip_line(self) -> None:
        self.take_line()

    # ------------------------------------------------------------------ model
    def parse(self) -> Model:
        model = Model(name="Model", source_type="xtUML DSL")
        try:
            self.skip_blank()
            if self.current().value == "domain":
                self.advance()
                if self.current().type in ("IDENT", "STRING"):
                    model.name = self.advance().value.strip('"\'')
                else:
                    self.error("Nama domain tidak ditemukan")
                self.expect("{")
                self.parse_body(model, closing="}")
            else:
                self.parse_body(model, closing=None)
        except ParseAbort:
            pass
        return model

    def parse_body(self, model: Model, closing: str | None) -> None:
        while self.current().type != "EOF":
            self.skip_blank()
            if self.current().type == "EOF" or (closing and self.current().value == closing):
                break
            keyword = self.current().value
            try:
                if keyword == "datatype":
                    model.datatypes.append(self.parse_datatype())
                elif keyword == "class":
                    model.classes.append(self.parse_class())
                elif keyword == "association":
                    model.associations.append(self.parse_association())
                elif keyword == "instance":
                    model.instances.append(self.parse_instance())
                elif keyword == "link":
                    model.links.append(self.parse_link())
                else:
                    self.error(f"Pernyataan '{keyword}' tidak dikenal di level domain")
                    self.skip_line()
            except ParseAbort:
                self.skip_line()
        if closing:
            try:
                self.expect("}")
            except ParseAbort:
                pass

    def parse_datatype(self) -> DataType:
        line = self.current().line
        self.advance()
        name = self.expect_ident().value
        base = "string"
        if self.current().value == "=":
            self.advance()
            tokens = self.take_line()
            base = self.text(tokens) or "string"
        return DataType(name=name, base=base)

    # ------------------------------------------------------------------ class
    def parse_class(self) -> ClassDef:
        line = self.current().line
        self.advance()
        name = self.expect_ident().value
        base = ""
        if self.current().value in ("extends", "is"):
            self.advance()
            base = self.expect_ident().value
        self.expect("{")

        class_def = ClassDef(name=name, base=base, line=line)
        while self.current().type != "EOF" and self.current().value != "}":
            self.skip_blank()
            if self.current().type == "EOF" or self.current().value == "}":
                break
            try:
                keyword = self.current().value
                if keyword == "attribute":
                    class_def.attributes.append(self.parse_attribute())
                elif keyword == "state" and self.current_index_next() == "machine":
                    class_def.state_machines.append(self.parse_state_machine())
                elif keyword == "operation":
                    class_def.operations.append(self.parse_operation())
                elif keyword == "event":
                    event = self.parse_event()
                    if class_def.state_machines:
                        class_def.state_machines[0].events.append(event)
                    else:
                        class_def.state_machines.append(
                            StateMachine(name="lifecycle", events=[event])
                        )
                else:
                    self.error(f"Anggota class '{keyword}' tidak dikenal")
                    self.skip_line()
            except ParseAbort:
                self.skip_line()
        self.expect("}")
        return class_def

    def current_index_next(self) -> str:
        if self.index + 1 < len(self.tokens):
            return self.tokens[self.index + 1].value
        return ""

    def parse_attribute(self) -> AttributeDef:
        line = self.current().line
        self.advance()
        tokens = self.take_line()
        if not tokens:
            self.error("Deklarasi attribute kosong")
            raise ParseAbort()
        name = tokens[0].value
        type_end = len(tokens)
        default = ""
        for index, token in enumerate(tokens):
            if token.value == "=":
                type_end = index
                default = self.text(tokens[index + 1 :])
                break
        colon = None
        for index, token in enumerate(tokens[:type_end]):
            if token.value == ":":
                colon = index
                break
        attr_type = self.text(tokens[colon + 1 : type_end]) if colon is not None else "any"
        return AttributeDef(name=name, type=attr_type or "any", default=default, line=line)

    def parse_operation(self) -> Operation:
        line = self.current().line
        self.advance()
        name = self.expect_ident().value
        params = self.parse_params()
        return_type = "void"
        if self.current().value == ":":
            self.advance()
            return_type = self.text(self.take_until({"{"})) or "void"
        body = self.parse_action_block()
        return Operation(name=name, params=params, return_type=return_type, body=body, line=line)

    def parse_params(self) -> list[Parameter]:
        self.expect("(")
        params: list[Parameter] = []
        while self.current().value != ")" and self.current().type != "EOF":
            tokens = self.take_until({",", ")"})
            if tokens:
                colon = next((i for i, t in enumerate(tokens) if t.value == ":"), None)
                if colon is None:
                    params.append(Parameter(name=tokens[0].value))
                else:
                    params.append(
                        Parameter(
                            name=tokens[0].value,
                            type=self.text(tokens[colon + 1 :]) or "any",
                        )
                    )
            if self.current().value == ",":
                self.advance()
        self.expect(")")
        return params

    # ---------------------------------------------------------- state machine
    def parse_state_machine(self) -> StateMachine:
        line = self.current().line
        self.advance()  # state
        self.advance()  # machine
        name = "lifecycle"
        if self.current().type == "IDENT":
            name = self.advance().value
        self.expect("{")
        machine = StateMachine(name=name, line=line)

        while self.current().type != "EOF" and self.current().value != "}":
            self.skip_blank()
            if self.current().type == "EOF" or self.current().value == "}":
                break
            try:
                keyword = self.current().value
                if keyword == "state":
                    machine.states.append(self.parse_state())
                elif keyword == "event":
                    machine.events.append(self.parse_event())
                elif keyword == "transition":
                    machine.transitions.append(self.parse_transition())
                else:
                    self.error(f"Anggota state machine '{keyword}' tidak dikenal")
                    self.skip_line()
            except ParseAbort:
                self.skip_line()
        self.expect("}")
        return machine

    def parse_state(self) -> State:
        line = self.current().line
        self.advance()
        name = self.expect_ident().value
        initial = False
        final = False
        while self.current().value in ("initial", "final"):
            if self.advance().value == "initial":
                initial = True
            else:
                final = True
        state = State(name=name, initial=initial, final=final, line=line)
        if self.current().value == "{":
            self.advance()
            while self.current().type != "EOF" and self.current().value != "}":
                self.skip_blank()
                if self.current().type == "EOF" or self.current().value == "}":
                    break
                label = self.current().value
                if label not in ("entry", "exit"):
                    self.error(f"Label '{label}' tidak dikenal di state; gunakan entry/exit")
                    self.skip_line()
                    continue
                self.advance()
                self.expect(":")
                statements = self.parse_statements({"exit", "}"})
                if label == "entry":
                    state.entry.extend(statements)
                else:
                    state.exit.extend(statements)
            self.expect("}")
        return state

    def parse_event(self) -> EventDef:
        line = self.current().line
        self.advance()
        name = self.expect_ident().value
        params = self.parse_params() if self.current().value == "(" else []
        return EventDef(name=name, params=params, line=line)

    def parse_transition(self) -> Transition:
        line = self.current().line
        self.advance()
        source = self.expect_ident().value
        self.expect("->")
        target = self.expect_ident().value
        self.expect("on")
        event = self.expect_ident().value
        guard = ""
        if self.current().value in ("when", "if"):
            self.advance()
            guard = self.text(self.take_until({"{"}))
        body = self.parse_action_block() if self.current().value == "{" else []
        return Transition(
            source=source, target=target, event=event, guard=guard, body=body, line=line
        )

    # ---------------------------------------------------------------- actions
    def parse_action_block(self) -> list[Statement]:
        self.expect("{")
        body = self.parse_statements({"}"})
        self.expect("}")
        return body

    def parse_statements(self, stops: set[str]) -> list[Statement]:
        statements: list[Statement] = []
        while self.current().type != "EOF" and self.current().value not in stops:
            self.skip_blank()
            if self.current().type == "EOF" or self.current().value in stops:
                break
            statement = self.parse_statement()
            if statement is not None:
                statements.append(statement)
        return statements

    def parse_statement(self) -> Statement | None:
        line = self.current().line
        if self.current().value == "if":
            return self.parse_if()
        if self.current().value == "while":
            return self.parse_while()

        tokens = self.take_line()
        if not tokens:
            return None
        head = tokens[0].value
        rest = tokens[1:]

        if head in ("log", "print"):
            expression = self.text(rest)
            if expression.startswith("(") and expression.endswith(")"):
                expression = expression[1:-1]
            return Statement(kind="log", expression=expression, line=line)

        if head in ("let", "var"):
            equals = next((i for i, t in enumerate(rest) if t.value == "="), None)
            if equals is None:
                self.error("Deklarasi variabel memerlukan '='", tokens[0])
                return None
            target = rest[0].value
            value_tokens = rest[equals + 1 :]
            if value_tokens and value_tokens[0].value == "create":
                class_name = value_tokens[1].value if len(value_tokens) > 1 else ""
                return Statement(kind="create", target=target, class_name=class_name, line=line)
            return Statement(kind="let", target=target, expression=self.text(value_tokens), line=line)

        if head == "create":
            class_name = rest[0].value if rest else ""
            target = rest[2].value if len(rest) > 2 and rest[1].value == "as" else ""
            return Statement(kind="create", target=target, class_name=class_name, line=line)

        if head == "return":
            return Statement(kind="return", expression=self.text(rest) or "undefined", line=line)

        if head == "delete":
            return Statement(kind="delete", expression=self.text(rest), line=line)

        if head in ("link", "unlink"):
            with_index = next((i for i, t in enumerate(rest) if t.value == "with"), None)
            via_index = next((i for i, t in enumerate(rest) if t.value in ("via", "on")), None)
            if with_index is None or via_index is None or via_index < with_index:
                self.error(f"Sintaks {head}: {head} <objek> with <objek> via <association>", tokens[0])
                return None
            source = self.text(rest[:with_index])
            target = self.text(rest[with_index + 1 : via_index])
            association = self.text(rest[via_index + 1 :])
            return Statement(
                kind=head, expression=source, target=target, class_name=association, line=line
            )

        if head == "generate":
            to_index = next((i for i, t in enumerate(rest) if t.value == "to"), None)
            if to_index is None:
                self.error("Sintaks generate: generate <Event> to <objek> [with <payload>]", tokens[0])
                return None
            event = self.text(rest[:to_index])
            following = rest[to_index + 1 :]
            with_index = next((i for i, t in enumerate(following) if t.value == "with"), None)
            if with_index is None:
                return Statement(kind="generate", expression=event, target=self.text(following), line=line)
            return Statement(
                kind="generate",
                expression=event,
                target=self.text(following[:with_index]),
                payload=self.text(following[with_index + 1 :]),
                line=line,
            )

        equals = next((i for i, t in enumerate(tokens) if t.value == "="), None)
        if equals is not None:
            return Statement(
                kind="assign",
                target=self.text(tokens[:equals]),
                expression=self.text(tokens[equals + 1 :]),
                line=line,
            )

        return Statement(kind="expr", expression=self.text(tokens), line=line)

    def parse_if(self) -> Statement:
        line = self.current().line
        self.advance()
        condition = self.collect_balanced("(", ")")
        body = self.parse_action_block()
        orelse: list[Statement] = []
        if self.current().value == "else":
            self.advance()
            if self.current().value == "if":
                nested = self.parse_if()
                orelse.append(nested)
            else:
                orelse = self.parse_action_block()
        return Statement(
            kind="if", expression=self.text(condition), body=body, orelse=orelse, line=line
        )

    def parse_while(self) -> Statement:
        line = self.current().line
        self.advance()
        condition = self.collect_balanced("(", ")")
        body = self.parse_action_block()
        return Statement(kind="while", expression=self.text(condition), body=body, line=line)

    # ---------------------------------------------------------- associations
    def parse_association(self) -> Association:
        line = self.current().line
        self.advance()
        name = self.expect_ident().value
        self.expect("between")
        first = self.parse_assoc_end()
        self.expect("and")
        second = self.parse_assoc_end()
        return Association(name=name, end_a=first, end_b=second, line=line)

    def parse_assoc_end(self) -> AssocEnd:
        line = self.current().line
        class_name = self.expect_ident().value
        role = class_name.lower()
        if self.current().value == ".":
            self.advance()
            role = self.expect_ident().value
        multiplicity = "1"
        if self.current().value == "[":
            multiplicity = self.text(self.collect_balanced("[", "]"))
        return AssocEnd(class_name=class_name, role=role, multiplicity=multiplicity, line=line)

    # ------------------------------------------------------------- instances
    def parse_instance(self) -> Instance:
        line = self.current().line
        self.advance()
        name = self.expect_ident().value
        self.expect("of")
        class_name = self.expect_ident().value
        values: dict[str, object] = {}
        if self.current().value == "{":
            self.advance()
            while self.current().type != "EOF" and self.current().value != "}":
                self.skip_blank()
                if self.current().type == "EOF" or self.current().value == "}":
                    break
                try:
                    tokens = self.take_line()
                    equals = next((i for i, t in enumerate(tokens) if t.value == "="), None)
                    if equals is None or equals == 0:
                        self.error("Atribut instance harus berbentuk name = nilai")
                        continue
                    attr_name = tokens[0].value
                    value_text = self.text(tokens[equals + 1 :])
                    values[attr_name] = literal_to_expr(parse_literal(value_text))
                except ParseAbort:
                    self.skip_line()
            self.expect("}")
        return Instance(name=name, class_name=class_name, values=values, line=line)

    def parse_link(self) -> Link:
        line = self.current().line
        self.advance()
        source = self.expect_ident().value
        self.expect("to")
        target = self.expect_ident().value
        self.expect("via")
        association = self.expect_ident().value
        return Link(association=association, source=source, target=target, line=line)
