from pydantic import ValidationError


def format_validation_error(error: ValidationError) -> str:
    lines: list[str] = []
    for item in error.errors(include_url=False):
        path = ".".join(str(part) for part in item["loc"])
        value = item.get("input")
        lines.append(f"{path}: {item['msg']}；收到 {value!r}")
    return "\n".join(lines)
