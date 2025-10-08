import spacy
from spacy.tokens import DocBin
from spacy.training.example import Example
import json
from pathlib import Path
import sys
import random
import shutil
from src.logger import log # Import our new centralized logger

# --- Configuration ---
BASE_DIR = Path(__file__).resolve().parent.parent
TRAINING_DATA_PATH = BASE_DIR / "data" / "training_data.jsonl"
MODELS_DIR = BASE_DIR / "models"
MODEL_OUTPUT_PATH = MODELS_DIR / "custom_ner_model"


def train_custom_ner_programmatically():
    """
    Trains a custom NER model programmatically to avoid potential issues with
    the config-based training pipeline and model serialization.
    """
    log.info("--- Starting programmatic NER model training ---")

    # 1. Load training data
    log.info(f"Loading training data from {TRAINING_DATA_PATH}")
    if not TRAINING_DATA_PATH.exists() or TRAINING_DATA_PATH.stat().st_size == 0:
        log.error(f"Training data not found or is empty at {TRAINING_DATA_PATH}.")
        sys.exit(1)

    training_data = []
    with TRAINING_DATA_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                training_data.append(json.loads(line))
            except json.JSONDecodeError:
                log.error("Error decoding JSON. Please check formatting.")
                continue
    log.info(f"Loaded {len(training_data)} training examples.")

    # 2. Create a blank spaCy model and add the NER pipe
    nlp = spacy.blank("en")
    log.info("Created blank 'en' model.")
    if "ner" not in nlp.pipe_names:
        ner = nlp.add_pipe("ner", last=True)
        log.info("Added 'ner' pipe to the model.")
    else:
        ner = nlp.get_pipe("ner")

    # 3. Add the custom entity label to the NER pipe
    for item in training_data:
        for span in item.get("spans", []):
            ner.add_label(span["label"])
    log.info("Added custom labels to the NER pipe.")

    # 4. Prepare training data in spaCy's Example format
    examples = []
    for item in training_data:
        text = item['text']
        annotations = {"entities": [(span['start'], span['end'], span['label']) for span in item.get('spans', [])]}
        try:
            example = Example.from_dict(nlp.make_doc(text), annotations)
            examples.append(example)
        except ValueError as e:
            log.warning(f"Skipping example due to ValueError: {e}. Text: '{text}'")
            continue
    log.info("Converted training data to spaCy Example objects.")

    # 5. Train the model
    n_iter = 25  # Number of training iterations
    other_pipes = [pipe for pipe in nlp.pipe_names if pipe != "ner"]
    with nlp.disable_pipes(*other_pipes):  # only train NER
        optimizer = nlp.begin_training()
        for itn in range(n_iter):
            random.shuffle(examples)
            losses = {}
            for example in examples:
                nlp.update([example], drop=0.35, sgd=optimizer, losses=losses)
            log.info(f"Iteration {itn+1}/{n_iter}, Losses: {losses}")

    # 6. Save the trained model to the 'model-best' subdirectory
    if MODEL_OUTPUT_PATH.exists():
        shutil.rmtree(MODEL_OUTPUT_PATH)
    best_model_path = MODEL_OUTPUT_PATH / "model-best"
    best_model_path.mkdir(parents=True, exist_ok=True)

    nlp.to_disk(best_model_path)
    log.info(f"--- Training complete. Model saved to {best_model_path} ---")


if __name__ == "__main__":
    train_custom_ner_programmatically()
    log.info("NER model training pipeline finished.")