from typing import List, Dict


def format_options(
    queryset, label_field="name", value_field="id"
) -> List[Dict[str, str]]:
    """
    Convert a queryset to a list of label/value pairs for dropdowns.
    """
    return [
        {"label": item[label_field], "value": str(item[value_field])}
        for item in queryset.values(value_field, label_field)
    ]
