import time
import json
from dotenv import load_dotenv
from chatbot_logic import get_ai_response

load_dotenv()

# 1. Evaluation dataset
eval_set = [
    {
        "question": "Яка вартість паркування?",
        "expected_keywords": ["40 грн", "300 грн"],
    },
    {
        "question": "Як оплатити паркування",
        "expected_keywords": ["готівк", "банківськ", "картк", "додат"],
    },
    {
        "question": "Чи є зарядні станції для електромобілів?",
        "expected_keywords": ["15", "електромобіл", "зарядк", "станці"],
    },
    {
        "question": "Який графік роботи паркінгу?",
        "expected_keywords": ["цілодобов"],
    }
]

def evaluate_rag():
    results = []
    total_latency = 0
    correct_hits = 0

    mock_session_data = {
    "Name": None,
    "Surname": None,
    "Plate": None,
    "StartDateTime": None,
    "EndDateTime": None
}

    print("Launch of the RAG system assessment...\n")

    for item in eval_set:
        start_time = time.time()
        
        # Calling RAG system
        response = get_ai_response(item["question"], mock_session_data)
        
        latency = time.time() - start_time
        total_latency += latency

        # Finding how many expected keywords are present in the response
        found_keywords = [word for word in item["expected_keywords"] if word.lower() in response.lower()]
        
        # Calculating recall@k (simplified as ratio of found keywords to expected keywords)
        recall_at_k = len(found_keywords) / len(item["expected_keywords"])
        is_correct = recall_at_k > 0.5  # Умовний поріг успіху

        if is_correct:
            correct_hits += 1

        results.append({
            "question": item["question"],
            "latency": round(latency, 2),
            "recall": round(recall_at_k, 2),
            "status": "✅" if is_correct else "❌"
        })

        print(f"Q: {item['question']}")
        print(f"Time: {round(latency, 2)}s | Recall: {round(recall_at_k, 2)} | {results[-1]['status']}")
        print("-" * 30)

    # Final metrics
    avg_latency = total_latency / len(eval_set)
    accuracy = (correct_hits / len(eval_set)) * 100

    print("\nFINAL REPORT:")
    print(f"Average latency (Latency): {round(avg_latency, 2)} seconds")
    print(f"Overall accuracy (Accuracy): {accuracy}%")
    
    # Saving detailed results to a JSON file
    with open("evaluation_report.json", "w", encoding="utf-8") as f:
        json.dump({
            "metrics": {"avg_latency": avg_latency, "accuracy": accuracy},
            "details": results
        }, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    evaluate_rag()