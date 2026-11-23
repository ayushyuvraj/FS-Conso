from pathlib import Path
from fs_conso.core.sample_generator import generate_benchmark_dataset, load_benchmark_raw_tbs
from fs_conso.agent.graph import build_consolidation_graph
from fs_conso.agent.state import ConsolidationState
from fs_conso.config import config

sample_dir = Path("inputs/sample_data")
generate_benchmark_dataset(sample_dir)
print("Generated benchmark dataset successfully!")

tbs = load_benchmark_raw_tbs(sample_dir)
print(f"Loaded {len(tbs)} benchmark raw TBs:")
for tb in tbs:
    print(f"  - {tb.entity_code}: {len(tb.rows)} rows, Currency={tb.currency}")

# Set a test active Gemini API key for testing the graph locally
config.gemini_api_key = "AIzaSyTestKeyActiveForConsolidationTesting"

app = build_consolidation_graph()
init_state = ConsolidationState(raw_tbs=tbs)
res = app.invoke(init_state)

print("Graph run complete!")
print("Final Step:", res["current_step"])
print("Teacher Score:", res.get("teacher_score", 0), "/ 100")
print("Output Excel:", res.get("output_excel_path"))
print("Teacher Evaluation:", res.get("teacher_evaluation"))
