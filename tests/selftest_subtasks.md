# Subtask check: planted-error self-test

20 subtasks the judge said MATCH, from 12 videos. Model: vllm / Qwen/Qwen3.8-27B. Errors: 0.

| Planted error | Expected | Caught |
|---|---|---|
| Task from an unrelated video on real frames + speech | NO | 20/20 (100%) |
| Real task on frames + speech from an unrelated video | NO | 20/20 (100%) |
| Original asked again | still YES/PARTLY | 20/20 (100%) |
| Every NO comes with a correct task | correct_task given | 40/40 |

## Misses


## Example corrections (task from an unrelated video)

- `14OIYdMNHS4` T3.2 (real: "Outline the regulatory and compliance steps required for an edible insect business."), planted "Describe the characteristics and advantages of tower systems for growing herbs, strawberries, and leafy greens." -> correct: "Describe the regulatory compliance and product development considerations for edible insect businesses."
- `G10TaIvf7So` T3.1 (real: "Explain how increasing the demand for agricultural crops to double as the world's population grows will require increased GAPs and effective input use."), planted "Demonstrate starting the engine and engaging the blade." -> correct: "Show a field of crops while discussing Good Agricultural Practices and smallholder productivity."
- `fG6mILlAenQ` T2.1 (real: "Note that Chinampas resulted in highly productive soil, increasing crop yields significantly."), planted "Note the significant benefits of precision farming, including reduced waste, environmental impact, and higher yields." -> correct: "Note the method used by Aztec farmers to construct their gardens, which involved piling mud and decaying vegetation to create highly productive soil."
- `-m1yW5F41Rs` T1.2 (real: "Note the forest walk with the narrator and a sister."), planted "Describe the concept of building a restaurant that sources directly from local farms." -> correct: "Mention the wildlife, such as elephants and snakes, seen during the visit to the island."
- `dmnBrbg3fvQ` T1.3 (real: "Describe the use of 0% interest credit cards to buy greenhouses and the strategy of using statement credits."), planted "Explain how vertical hydroponic farming optimizes space and resource use." -> correct: "Explain how to fund greenhouse construction using 0% interest business credit cards."
- `YwZtvMELRrM` T1.2 (real: "Describe the benefits of high moisture hay versus dry hay."), planted "Note the significant benefits of precision farming, including reduced waste, environmental impact, and higher yields." -> correct: "Note the benefits of high moisture hay, including nutrient retention and protection from weather."