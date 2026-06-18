# Lock: current outfit versus received uniform

This lock fixes a recurring state bug: the engine sometimes treats issued Academy uniform as currently worn clothing.

## Rule

Received uniform is not the same as worn uniform.

If the scene says the Academy issued a uniform, store it separately from current clothing.

Use separate state concepts:

```json
{
  "current_outfit": "what Akira is actually wearing right now",
  "received_uniform": ["burgundy academy blazer", "skirt"],
  "carried_items": ["phone", "bag", "received uniform if carried"]
}
```

## Writing visible_inventory

Do not write this:

```json
"одежда: высокие ботинки, чёрная юбка-шорты, чёрная рубашка, бордовый пиджак Академии"
```

unless the scene explicitly states that Akira is already wearing the Academy uniform.

Write this instead when the uniform was only issued:

```json
"текущая одежда: обычная спортивная одежда"
"полученная форма Академии: бордовый пиджак и юбка, ещё не надета"
```

## Apply-turn-result requirement

When clothes or uniform status changes, current_state_changes must include explicit fields:

```json
{
  "current_state_changes": {
    "current_outfit": "...",
    "received_uniform": ["..."],
    "uniform_worn": false,
    "visible_inventory": ["..."]
  }
}
```

## Gameplay rendering

The header and prose must use current_outfit for what is on the body.

The received_uniform may appear as an object, carried item, folded clothing, package, bag content, or nearby item, but not as worn clothing unless uniform_worn is true.

## Player control

Do not dress Akira into the uniform unless:
- the player says she changes clothes;
- the scene explicitly applies a uniform change;
- saved current_state says uniform_worn is true.
