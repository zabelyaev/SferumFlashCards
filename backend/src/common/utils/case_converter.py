def camel_case_to_snake_case(inp_text: str) -> str:
    out = "".join(f"_{i.lower()}" if i.isupper() else i for i in inp_text)
    return out[1:] if out[0] == "_" else out
