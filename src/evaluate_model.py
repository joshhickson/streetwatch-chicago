import spacy
from src.logger import log

# --- Configuration ---
# A sample sentence that contains a Chicago-specific location format
# that the default spaCy model is likely to miss.
SAMPLE_TEXT = "There was a major checkpoint at Milwaukee and Damen, right by the blue line stop."

# Paths to the models
DEFAULT_MODEL = "en_core_web_sm"
CUSTOM_MODEL_PATH = "models/custom_ner_model/model-best"

def evaluate_models():
    """
    Loads both the default and custom spaCy models and runs them on a sample
    text to provide a side-by-side comparison of their entity recognition.
    """
    log.info("--- Starting Model Evaluation ---")

    # --- 1. Load and Evaluate Default Model ---
    log.info(f"Loading default model: '{DEFAULT_MODEL}'")
    try:
        nlp_default = spacy.load(DEFAULT_MODEL)
        log.info("Processing text with default model...")
        doc_default = nlp_default(SAMPLE_TEXT)

        print("\n--- Entities found by DEFAULT model: ---")
        if doc_default.ents:
            for ent in doc_default.ents:
                print(f"  - Entity: '{ent.text}', Label: '{ent.label_}'")
        else:
            print("  No entities found.")

    except Exception as e:
        log.error(f"Could not load or run the default model. Error: {e}", exc_info=True)

    print("-" * 40)

    # --- 2. Load and Evaluate Custom Model ---
    log.info(f"Loading custom model from: '{CUSTOM_MODEL_PATH}'")
    try:
        nlp_custom = spacy.load(CUSTOM_MODEL_PATH)
        log.info("Processing text with custom model...")
        doc_custom = nlp_custom(SAMPLE_TEXT)

        print("\n--- Entities found by CUSTOM model: ---")
        if doc_custom.ents:
            for ent in doc_custom.ents:
                print(f"  - Entity: '{ent.text}', Label: '{ent.label_}'")
        else:
            print("  No entities found.")

    except Exception as e:
        log.error(f"Could not load or run the custom model. Make sure you have trained it first by running 'src/train_ner.py'. Error: {e}", exc_info=True)

    log.info("--- Model Evaluation Finished ---")


if __name__ == "__main__":
    evaluate_models()