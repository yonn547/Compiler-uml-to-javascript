# Referensi format model

## 1. DSL xtUML (disarankan)

File berekstensi `.xtuml`. Komentar: `# ...` atau `// ...`. Pernyataan diakhiri baris baru atau `;`; blok memakai `{ ... }`.

```txt
domain <NamaDomain> {
  datatype <Nama> = <tipe dasar>

  class <Nama> [extends <Induk>] {
    attribute <nama> : <tipe> [= <ekspresi>]
    event <Event>[(param : tipe, ...)]

    state machine <nama> {
      event <Event>[(param : tipe, ...)]
      state <nama> [initial] [final] {
        entry: <statement>
        exit:  <statement>
      }
      transition <dari> -> <ke> on <Event> [when <ekspresi>] {
        <statement>
      }
    }

    operation <nama>(param : tipe, ...) : <tipe> {
      <statement>
    }
  }

  association <nama> between <ClassA>.<roleA> [<multA>] and <ClassB>.<roleB> [<multB>]

  instance <nama> of <Class> {
    <atribut> = <literal>
  }
  link <instanceA> to <instanceB> via <association>
}
```

`domain` boleh dihilangkan untuk model kecil. Multiplicity: `1`, `0..1`, `0..*`, `1..*`, `*`.

**Semantics association**: `<roleA>` dipasang sebagai property pada `ClassA`, dan `<multA>` menentukan berapa banyak objek `ClassB` yang bisa ditautkan dari satu objek `ClassA`. Jadi `Customer.orders [0..*]` berarti `customer.orders` adalah array; `Order.customer [1]` berarti `order.customer` satu objek (atau `null`).

### Action language yang didukung

| Pernyataan | Contoh | Output JS |
|---|---|---|
| log | `log("halo")` | `console.log("halo");` |
| deklarasi | `let total = 0` | `let total = 0;` |
| assignment | `self.total = total + 1` | `this.total = total + 1;` |
| return | `return total` | `return total;` |
| if/else | `if (x > 0) { ... } else { ... }` | sama |
| while | `while (x > 0) { ... }` | sama |
| create | `let o = create Order` | `let o = new Order();` |
| delete | `delete o` | `UmlObject.registry.remove(o);` |
| link | `link o with c via placedOrder` | `assoc_placedOrder.link(o, c);` |
| unlink | `unlink o with c via placedOrder` | `assoc_placedOrder.unlink(o, c);` |
| generate | `generate confirm to o with payload` | `o.generate("confirm", payload);` |
| call | `o.label()` | `o.label();` |

Ekspresi: literal string/number/boolean/null, `self`, atribut, operator `+ - * / %`, perbandingan `== != < > <= >=`, `and/or/not`, `mod/div`, pemanggilan method. `self` diterjemahkan menjadi `this`.

## 2. XML xtUML

```xml
<xtuml name="Shop">
  <datatype name="Money" base="real"/>
  <class name="Order">
    <attribute name="total" type="Money"/>
    <state-machine name="lifecycle">
      <event name="confirm"/>
      <state name="pending" initial="true">
        <entry>log("order baru")</entry>
        <exit>log("selesai")</exit>
      </state>
      <state name="paid" final="true"/>
      <transition from="pending" to="paid" event="confirm" guard="self.total &gt; 0">
        log("lunas")
      </transition>
    </state-machine>
    <operation name="label" return="string">
      <body>return "Order";</body>
    </operation>
  </class>

  <association name="placedOrder">
    <end class="Customer" role="orders" multiplicity="0..*"/>
    <end class="Order" role="customer" multiplicity="1"/>
  </association>

  <instance name="o1" class="Order">
    <attribute name="total">150000</attribute>
  </instance>
  <link association="placedOrder" source="c1" target="o1"/>
</xtuml>
```

Format lama `<uml><object .../><link .../></uml>` juga masih diterima dan diubah ke IR yang sama.

## 3. JSON / IR kanonik

Gunakan hasil `--ir` atau tombol *Simpan IR*. Root memiliki `"kind": "xtuml-model"`, `"version": 1`, dan array `classes`, `associations`, `instances`, `links`, `datatypes`. Format lama `{"objects": [...], "links": [...]}` juga diterima.

## 4. PlantUML (kompatibel lama)

```txt
object user1 {
  name = "Alice"
  age = 28
}

class Order {
  total : real
}

user1 -- order1 : placedOrder
```

Object diubah menjadi instance + class otomatis; link diubah menjadi association + link instance.
