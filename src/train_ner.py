import spacy
from spacy.tokens import DocBin
import json
from pathlib import Path
import sys
import os
from src.logger import log # Import our new centralized logger

# --- Configuration ---
BASE_DIR = Path(__file__).resolve().parent.parent
TRAINING_DATA_PATH = BASE_DIR / "data" / "training_data.jsonl"
MODELS_DIR = BASE_DIR / "models"
CONFIG_PATH = MODELS_DIR / "config.cfg"
TRAINING_BINARY_PATH = MODELS_DIR / "training_data.spacy"
MODEL_OUTPUT_PATH = MODELS_DIR / "custom_ner_model"


def convert_data_for_training(training_data_path: Path, output_path: Path):
    """Converts annotated data from JSONL format to spaCy's binary format."""
    log.info("--- Step 1: Converting data for training ---")
    if not training_data_path.exists() or training_data_path.stat().st_size == 0:
        log.error(f"Training data not found or is empty at {training_data_path}. Please provide annotated data.")
        sys.exit(1)

    nlp = spacy.blank("en")
    db = DocBin()

    line_count = 0
    with training_data_path.open("r", encoding="utf-8") as f:
        for line in f:
            line_count += 1
            try:
                data = json.loads(line)
                doc = nlp.make_doc(data['text'])
                ents = []
                for span in data.get("spans", []):
                    span_obj = doc.char_span(span["start"], span["end"], label=span["label"], alignment_mode="contract")
                    if span_obj is None:
                        log.warning(f"Skipping entity in line '{data['text']}' - span '{data['text'][span['start']:span['end']]}' is not a valid token boundary.")
                    else:
                        ents.append(span_obj)
                doc.ents = ents
                db.add(doc)
            except json.JSONDecodeError:
                log.error(f"Error decoding JSON on line {line_count}. Please check formatting.")
                continue

    output_path.parent.mkdir(parents=True, exist_ok=True)
    db.to_disk(output_path)
    log.info(f"Successfully converted {line_count} lines of data to {output_path}")


def generate_training_config():
    """Generates a base spaCy config file for training."""
    log.info("--- Step 2: Generating spaCy config file ---")
    MODELS_DIR.mkdir(exist_ok=True)

    command = f"python -m spacy init config {CONFIG_PATH} --lang en --pipeline ner --optimize efficiency --force"
    log.info(f"Executing config generation command: {command}")
    os.system(command)

    log.info(f"Base config file generated at {CONFIG_PATH}")


def run_model_training():
    """Runs the spaCy training process using the generated config and data."""
    log.info("--- Step 3: Starting model training ---")
    if not CONFIG_PATH.exists():
        log.critical(f"Config file not found at {CONFIG_PATH}. Cannot start training.")
        sys.exit(1)

    command = (
        f"python -m spacy train {CONFIG_PATH} "
        f"--output {MODEL_OUTPUT_PATH} "
        f"--paths.train {TRAINING_BINARY_PATH} "
        f"--paths.dev {TRAINING_BINARY_PATH}"
    )

    log.info(f"Executing training command:\n{command}")
    os.system(command)

    log.info(f"--- Training complete. Best model saved to {MODEL_OUTPUT_PATH / 'model-best'} ---")


if __name__ == "__main__":
    log.info("Starting custom NER model training pipeline.")
    convert_data_for_training(TRAINING_DATA_PATH, TRAINING_BINARY_PATH)
    generate_training_config()
    run_model_training()
    log.info("NER model training pipeline finished.")