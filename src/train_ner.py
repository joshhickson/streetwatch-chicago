import spacy
from spacy.tokens import DocBin
import json
from pathlib import Path
import sys
import os

# --- Configuration ---
# Define the paths to the various files and directories we'll be using.
# This makes the script easier to read and maintain.
BASE_DIR = Path(__file__).resolve().parent.parent
TRAINING_DATA_PATH = BASE_DIR / "data" / "training_data.jsonl"
MODELS_DIR = BASE_DIR / "models"
CONFIG_PATH = MODELS_DIR / "config.cfg"
BASE_CONFIG_PATH = MODELS_DIR / "base_config.cfg"
TRAINING_BINARY_PATH = MODELS_DIR / "training_data.spacy"
MODEL_OUTPUT_PATH = MODELS_DIR / "custom_ner_model"


def convert_data_for_training(training_data_path: Path, output_path: Path):
    """
    Converts annotated data from JSONL format to spaCy's binary format.
    This is a necessary preprocessing step for training.
    """
    print("--- Converting data for training ---")
    if not training_data_path.exists():
        print(f"Error: Training data not found at {training_data_path}", file=sys.stderr)
        sys.exit(1)

    # Use a blank English model as a base.
    nlp = spacy.blank("en")
    db = DocBin()

    with training_data_path.open("r", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            doc = nlp.make_doc(data['text'])
            ents = []
            for span in data.get("spans", []):
                # Create a spaCy Span object from the character indices.
                # 'alignment_mode="contract"' helps handle cases where spans
                # might not perfectly align with token boundaries.
                span_obj = doc.char_span(span["start"], span["end"], label=span["label"], alignment_mode="contract")
                if span_obj is None:
                    print(f"Warning: Skipping entity in line '{data['text']}' - span '{data['text'][span['start']:span['end']]}' is not a valid token boundary.", file=sys.stderr)
                else:
                    ents.append(span_obj)
            doc.ents = ents
            db.add(doc)

    # Ensure the output directory exists.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    db.to_disk(output_path)
    print(f"Successfully converted data to {output_path}")


def generate_training_config():
    """
    Generates a spaCy config file for training by creating and filling a base config.
    This is the recommended approach using spaCy's own CLI tools.
    """
    print("--- Generating spaCy config file ---")
    MODELS_DIR.mkdir(exist_ok=True)

    # Generate a base config for an NER pipeline, optimizing for efficiency (faster, smaller model).
    # --force will overwrite an existing base config.
    os.system(f"python -m spacy init config {BASE_CONFIG_PATH} --lang en --pipeline ner --optimize efficiency --force")

    # Fill the base config with our specific paths.
    # We use the same data for training and development for simplicity.
    os.system(f"python -m spacy init fill-config {BASE_CONFIG_PATH} {CONFIG_PATH} --train-path {TRAINING_BINARY_PATH} --dev-path {TRAINING_BINARY_PATH}")

    print(f"Config file generated at {CONFIG_PATH}")


def run_model_training():
    """
    Runs the spaCy training process using the generated config and data.
    """
    print("--- Starting model training ---")
    if not CONFIG_PATH.exists():
        print(f"Error: Config file not found at {CONFIG_PATH}", file=sys.stderr)
        sys.exit(1)

    # Use the 'spacy train' command. This will train the model and save the best
    # performing version to the specified output path.
    os.system(f"python -m spacy train {CONFIG_PATH} --output {MODEL_OUTPUT_PATH}")

    print(f"--- Training complete. Best model saved to {MODEL_OUTPUT_PATH / 'model-best'} ---")


if __name__ == "__main__":
    # This script is designed to be run from the command line.
    # It executes the three main steps in order.

    # 1. Convert the annotated data into the format spaCy needs.
    convert_data_for_training(TRAINING_DATA_PATH, TRAINING_BINARY_PATH)

    # 2. Generate the configuration file for the training process.
    generate_training_config()

    # 3. Run the training process.
    run_model_training()