"""Petit pipeline de traitement — fichier de démonstration pour nodal."""

import json
import os
from pathlib import Path


def load_config(path):
    raw = Path(path).read_text()
    data = json.loads(raw)
    return validate(data)


def validate(data):
    if "input" not in data:
        raise ValueError("clé 'input' manquante")
    return data


def normalize(text):
    return text.strip().lower()


class Pipeline:
    def __init__(self, config):
        self.config = validate(config)
        self.store = Store(config.get("db", "out.db"))

    def run(self):
        text = self.read_source()
        clean = normalize(text)
        result = self.transform(clean)
        self.store.save(result)
        return result

    def read_source(self):
        path = self.config["input"]
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        return open(path).read()

    def transform(self, text):
        words = text.split()
        return {"count": len(words), "words": sorted(set(words))}


class Store:
    def __init__(self, path):
        self.path = path

    def save(self, payload):
        blob = json.dumps(payload, indent=2)
        Path(self.path).write_text(blob)


def main():
    config = load_config("config.json")
    pipe = Pipeline(config)
    pipe.run()
    print("terminé")


if __name__ == "__main__":
    main()
