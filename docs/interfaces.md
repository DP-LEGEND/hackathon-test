# Interfaces between pieces

Agree these on Saturday at 11:00, before anyone builds. Each piece reads and writes exactly these formats.

## core → agent
_(example shape, replace on Saturday)_
```json
{ "metrics": {}, "flags": [] }
```

## agent → frontend
```json
{ "summary": "", "actions": [] }
```
