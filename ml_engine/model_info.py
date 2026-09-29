import json

from predict import load_model


def model_info():
    """Options for the prediction form, taken from the trained model."""
    m = load_model()
    groups = sorted(g for g in m["categorical"]["genre_group"] if g != "Other")
    publishers = sorted(p for p, v in m["publishers"].items() if v["games"] >= 2 and p != "Unknown")
    return {
        "genre_groups": groups,
        "publishers": publishers,
        "coverage": m["coverage_target"],
        "trained_on": m["trained_on"],
    }


if __name__ == "__main__":
    print(json.dumps(model_info()))
