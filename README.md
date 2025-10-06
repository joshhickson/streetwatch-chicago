# StreetWatch Chicago: Automated ICE & CBP Activity Mapping

This repository contains the backend service for a real-time geospatial intelligence pipeline designed to map ICE and CBP activity in Chicago based on publicly available social media data. The project is detailed in the [Automated ICE Map Workflow document](10.04.2025%20Automated%20ICE%20Map%20Workflow.md).

## Project Overview

The system is designed as a data pipeline that automates the following processes:
1.  **Ingestion:** Monitors social media (initially Reddit) for relevant posts.
2.  **Processing & Enrichment:** Uses Natural Language Processing (NLP) to extract locations, then geocodes them to get precise coordinates.
3.  **Storage & Formatting:** Stores the processed data in a structured CSV format, ready for visualization.
4.  **Visualization:** The generated CSV can be imported into Google MyMaps to create an interactive map of sightings.

## Important Note for Cloning (Git LFS)

This repository uses [Git LFS (Large File Storage)](https://git-lfs.github.com/) to manage the large model files located in the `models/` directory.

After cloning the repository, you **must** run the following command to download the model files:
```bash
git lfs pull
```
This will ensure that the application has the necessary models to function correctly. Both human and AI developers need to perform this step.

## Current Status: Phase 1 Complete

The initial Python backend, built with Flask, is now complete and has been submitted for review. This version includes the core logic for processing sighting reports.
This was a significant update. Here is a summary of everything that's now included:

New Logging System: The application now has a robust, centralized logger that creates a unique, timestamped log file for every run. This will be invaluable for monitoring the automated processes.
Complete AI Training Pipeline: You now have all the tools to create and improve your own custom AI models for location extraction. This includes:
The data/training_data.jsonl file with the latest 14 examples you provided.
The training script src/train_ner.py to build a new model from that data.
The evaluation script src/evaluate_model.py to compare your custom model's performance against the default one.
Our First Custom Model: The first version of our custom-trained model is included. Given the environment issues we faced, you may want to run the training script yourself to ensure you have a perfectly clean version.
What's next?

The automated data fetching process (the GitHub Action) will now start using this new, more intelligent model to find sightings. You can add more data to data/training_data.jsonl and re-run the training script at any time to make the system even smarter.

This project follows the phased implementation plan outlined in the main workflow document.

## Progress Update: 2025-10-05

The custom NER model has been successfully re-trained using the latest data in `data/training_data.jsonl`. The trained model files are now included in the `models/` directory and will be checked into version control.

**Key Accomplishments:**
*   **Model Trained:** The spaCy NER model was trained successfully.
*   **Repository Updated:** The `.gitignore` file was updated to ensure the trained model is committed to the repository.
*   **Tests Passed:** The application's test suite (`test_endpoint.py`) was executed and all tests passed, verifying the functionality with the new model.

**Note:** An attempt to get an automated code review failed because the trained model files are too large for the review tool to handle.

### Next Steps

#### For Jules (AI Assistant):
*   Awaiting feedback from the human-in-the-loop.
*   If approved, proceed with submitting the changes to the repository.

#### For Humans (Project Team):
*   Please review the changes.
*   Advise on whether to proceed with committing the changes without a formal code review.
*   To further improve accuracy, consider annotating more examples in `data/training_data.jsonl`. The model can be easily retrained by running `python -m src.train_ner`.
