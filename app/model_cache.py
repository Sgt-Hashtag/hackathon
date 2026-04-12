from sentence_transformers import SentenceTransformer

def download():
    model_name = "all-MiniLM-L6-v2"
    save_path = "/models/sentence-transformers_all-MiniLM-L6-v2"

    print(f"📦 Downloading {model_name} and saving to {save_path}...")
    model = SentenceTransformer(model_name)
    model.save(save_path)
    print("✅ Model saved successfully.")

if __name__ == "__main__":
    download()