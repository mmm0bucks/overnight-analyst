# 0002 — The agent never writes; a publisher does

**Status:** accepted

**Context.** The vault contains human notes. State (the hypothesis backlog) is the
agent's memory between runs; corrupting it silently poisons every later run.

**Decision.** Agent tools are read-only. One module, the publisher, writes vault and
state: atomically (temp file + rename), with a backup of what it replaces, with secret
redaction, and only inside `<!-- overnight:begin/end -->` markers in shared notes.
State is updated only by runs whose gates all passed.

**Consequences.** A bad model output can at worst produce a bad report marked `partial`;
it cannot damage notes or memory.
