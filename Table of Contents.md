---
aliases: [TOC, Index, Map of Content]
tags: [index, master]
type: overview
---
# 1. Foundational Mathematics & Statistics
[LibreTexts Mathematics](https://math.libretexts.org/)
## 1.1. Linear Algebra
### 1.1.1. Core Concepts:
- [[Overview - Linear Algebra]]
	- Vectors, matrices, and matrix operations 
		- ([Khan Academy: Vectors and spaces](https://www.khanacademy.org/math/linear-algebra/vectors-and-spaces))
	- Linear transformations, Systems of linear equations
	- Dot products, cross products
### 1.1.2. Advanced Topics for AI:
- Eigenvalues and eigenvectors ([3Blue1Brown: Eigenvectors and eigenvalues](https://www.youtube.com/watch?v=PFDu9oVAE-g&list=PLZHQObOWTQDPD3MizzM2xVFitgF8hE_ab&index=14))
- Singular Value Decomposition (SVD) ([Stanford CS229: SVD Review](https://cs229.stanford.edu/section/cs229-svd.pdf))
- Principal Component Analysis (PCA) ([StatQuest: PCA explained](https://www.youtube.com/watch?v=FgakZw6K1QQ))
- Tensors and tensor operations (especially for Deep Learning) ([TensorFlow: Introduction to Tensors](https://www.tensorflow.org/guide/tensor))
### 1.1.3. Where to Learn:
- [Essence of Linear Algebra (YouTube - 3Blue1Brown)](https://www.youtube.com/playlist?list=PLZHQObOWTQDPD3MizzM2xVFitgF8hE_ab) - Highly intuitive visual explanations.
- [Khan Academy: Linear Algebra](https://www.khanacademy.org/math/linear-algebra)
- [Mathematics for Machine Learning Specialization (Coursera)](https://www.coursera.org/specializations/mathematics-machine-learning)

## 1.2. Probability & Statistics
Resources:
	[NIST/SEMATECH e-Handbook of Statistical Methods](https://www.itl.nist.gov/div898/handbook/index.htm)
### 1.2.1. Core Concepts:
#### Descriptive statistics & Probability theory
- Mean, Median, Mode, Variance, Standard Deviation
- Sample spaces, conditional probability
- Bayes’ Theorem ([3Blue1Brown](https://www.youtube.com/watch?v=HZGCoVF3YvM))
#### [[Probability Distributions]]
- Normal, Poisson, Binomial, Uniform
### 1.2.2. Advanced Topics for AI:
- Hypothesis testing & p-values, confidence intervals
- Regression analysis (Linear, Logistic - covered further in ML)
- Markov Chains, Hidden Markov Models (HMMs) - (Core for classical NLP)
- Information Theory: Entropy, Mutual Information, KL Divergence ([Visual Information Theory](https://colah.github.io/posts/2015-09-Visual-Information/))

## 1.3. Calculus & Optimization
### 1.3.1. Core Concepts:
- [[Calculus Overview]]
- [[Differentiation & Partial Derivatives]]
- Integrals and Multivariable calculus
### 1.3.2. Optimization Techniques for AI:
- [Gradient Descent](https://www.youtube.com/watch?v=IHZwWFHWa-w) (StatQuest) and its variants (SGD, Adam, etc.)
- Loss functions, cost functions
- Convex optimization 

# 2. Programming & Software Engineering
## 2.1. Core Programming Languages
### 2.1.1. [[Python]]
The dominant language for AI/ML and Agentic Workflows.
- Fundamentals: Data types, loops, classes, async/await (crucial for API calls).
- Key Libraries for AI:
- [[NumPy]] : Numerical computing, N-dimensional arrays.
- [Pandas](https://pandas.pydata.org/docs/user_guide/10min.html): Data manipulation.
- [Scikit-learn](https://scikit-learn.org/stable/user_guide.html): Core machine learning library.
- [PyTorch](https://pytorch.org/tutorials/): Deep learning frameworks.
- Requests / AIOHTTP / Pydantic: Crucial for building and interacting with Agent APIs.

### 2.1.2. Web Technologies (For Browser Agents)
- DOM (Document Object Model) manipulation.
- HTML/CSS structures (XPath, CSS Selectors) for agent web scraping.
- JavaScript basics for understanding client-side rendering.

### 2.1.3. Other Languages
- **C++**: Critical for performance-intensive AI (CUDA kernels, physics simulations).
- **TypeScript**: Increasingly popular for Agent frameworks (LangChain.js, specialized desktop apps).
- **SQL / Shell Scripting (Bash)**: Essential for data pulling and CLI integrations.

## 2.2. Software Engineering Practices
- Version Control (Git) and CI/CD (GitHub Actions)
- Testing: `pytest`, mocking API calls (crucial for testing LLM outputs).
- API Design: RESTful principles, GraphQL, OpenAPI/Swagger specifications (how LLMs read APIs).

# 3. Machine Learning Fundamentals
[Machine Learning Glossary]([Supervised Learning](https://developers.google.com/machine-learning/glossary#supervised-learning))
## 3.1. Types of Learning
- [[Supervised Learning]]: Learning from labeled data (Classification & Regression).
- [Unsupervised Learning](https://developers.google.com/machine-learning/glossary#unsupervised-learning): Clustering (K-Means), Dimensionality Reduction (PCA).
- Reinforcement Learning: Reward-based learning in environments.
- Self-Supervised Learning: (The foundation of modern LLMs).

## 3.2. Model Evaluation & Metrics
- Train-validation-test split, Cross-Validation.
- Metrics: Accuracy, Precision, Recall, F1-score, MSE.
- [Bias-Variance Tradeoff](https://en.wikipedia.org/wiki/Bias%E2%80%93variance_tradeoff), Overfitting/Underfitting. Regularization techniques (L1, L2).

## 3.3. Common Machine Learning Algorithms
- Linear & Logistic Regression
- Tree-Based Models: Decision Trees, Random Forests, Gradient Boosting (XGBoost).
- SVMs, K-Nearest Neighbors (KNN).

# 4. Deep Learning (DL)
## 4.1 Neural Network Fundamentals
- Neurons, Layers, Activation Functions (Sigmoid, ReLU, GELU).
- Forward Propagation & Backpropagation.
- Optimizers (Adam, RMSprop) and Loss Functions (Cross-Entropy).

## 4.2 Deep Learning Architectures
- **CNNs (Convolutional Neural Networks):** Image and video processing (ResNet, YOLO).
- **RNNs & LSTMs:** Sequential data processing (legacy NLP).
- **Transformers:** The definitive architecture for modern AI (Self-Attention mechanism). 
  - [The Illustrated Transformer (Jay Alammar)](http://jalammar.github.io/illustrated-transformer/)

## 4.3 Generative AI Advanced Concepts
- **Large Language Models (LLMs):** Pre-training vs. Instruction Fine-Tuning vs. RLHF.
- **Diffusion Models:** Image and video generation (Stable Diffusion, Midjourney, Sora).
- **Multi-Modal Models:** Vision-Language Models (VLMs) like GPT-4o, Claude 3.5 Sonnet.

# 5. Natural Language Processing (NLP) & Vector Search
## 5.1. Core NLP & Embeddings
- Text Representation: Word2Vec, Contextual Embeddings.
- [[Vector Embeddings]]: Dense representations of text.
- [[Vector Databases]]: ChromaDB, Pinecone, [Milvus](https://milvus.io/intro), Qdrant. 
- Chunking strategies for parsing large documents.

## 5.2. Post-Training & Application
- **[[Prompt Engineering]]:** System prompts, few-shot prompting, prompt injection defenses.
- **[[Retrieval Augmented Generation (RAG)]]:** Connecting LLMs to external data via Vector DBs.
  - Advanced RAG: Semantic routing, query rewriting, re-ranking (Cohere).
- Fine-Tuning: LoRA, QLoRA, Parameter-Efficient Fine-Tuning (PEFT).

# 6. Intelligent Agents & Autonomy
## 6.1. [[AI Agents]]
### 6.1.1. Modern LLM-Based Agents
- Core Architectures: ReAct (Reason + Act), Plan-and-Solve, Reflexion, Chain of Thought (CoT).
- Memory Systems: Short-term (context window) vs. Long-term (Vector DBs).
- Agent Personalities & System Prompts: Directing autonomous behavior safely.

### 6.1.2. Agent Tool Use & Integration (The "Hands")
- [[Function Calling & Structured Outputs]]: The bridge between LLMs and code (JSON schemas).
- API Integration:
  - Defining OpenAPI specs for agents.
  - Authentication (OAuth, API keys).
- CLI & Environment Integration:
  - Sandboxed execution (Docker enclosures).
  - Executing bash/shell commands dynamically.
- Web & Browser Automation:
  - DOM parsing and vision-based elements extraction.
  - Frameworks: Playwright, Puppeteer.

### 6.1.3. Agent Frameworks & Platforms
- **Orchestration:** [LangChain](https://python.langchain.com/), [LlamaIndex](https://www.llamaindex.ai/) (Best for RAG).
- **Multi-Agent Systems:** [CrewAI](https://www.crewai.com/), [Microsoft AutoGen](https://microsoft.github.io/autogen/), [OpenAI Swarm](https://github.com/openai/swarm).
- **Autonomous Coding Agents:** [OpenHands (formerly OpenDevin)](https://github.com/All-Hands-AI/OpenHands), Open Interpreter, Devin/Devika, Cline/Antigravity.
- **Tool Protocols:** [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) (Standardizing tool access for models).

### 6.1.4. Evaluation & Safety for Agents
- Guardrails and bounds (e.g., restricting file paths, enforcing API limits).
- Benchmarking: SWE-bench (coding), WebArena (browser use).
- Preventing prompt injection and unauthorized actions.

# 7. Data Processing, Engineering & MLOps
## 7.1. Data Collection & Pipelines
- Web scraping (BeautifulSoup, Scrapy), API ingestion.
- Data Storage: SQL vs NoSQL, Data Lakes, Data Warehouses.
- Feature Engineering: Normalization, encoding, handling missing data.

## 7.2. MLOps (Machine Learning Operations) & Deployment
- Model deployment, serving architectures (vLLM, Ollama for local LLMs).
- Containerization: Docker, Kubernetes.
- Cloud AI: AWS Bedrock, GCP Vertex AI, Azure OpenAI.
- Monitoring: Tracking token usage, latency, and LLM hallucinations (LangSmith, Helicone).

# 8. Computer Vision (CV)
## 8.1 Core Concepts
- Image Preprocessing: OpenCV, Filtering, transformations.
- Object Detection: YOLO, SSD.
- Image Segmentation: Semantic vs. Instance.
- 3D Computer Vision: Point clouds, SLAM (Visual localization).
- Vision Transformers (ViT) and cross-modal implementations.

# 9. Reinforcement Learning (RL)
## 9.1. Core Concepts
- Markov Decision Processes (MDPs), value & policy iteration.
- Algorithms: Q-Learning, Policy Gradients, PPO (Proximal Policy Optimization).
- Deep Reinforcement Learning (DRL).
- RLHF (Reinforcement Learning from Human Feedback) & RLAIF (from AI Feedback).

# 10. Robotics (Hardware & Control Systems)
## 10.1. Kinematics, Dynamics & Control
- Forward/Inverse Kinematics.
- PID controllers, State-space representation, Model Predictive Control (MPC).
## 10.2. Sensors, Actuators & ROS
- Cameras, LiDAR, IMUs. Motor controllers.
- Robot Operating System ([ROS 2](https://docs.ros.org/en/rolling/)). Nodes, Topics, Messages.
- Simulation: Gazebo, NVIDIA Isaac Sim, MuJoCo.

# 11. AI Ethics, Safety & Governance
- Explainable AI (XAI) & Interpretability (LIME, SHAP).
- Bias, Fairness, and Copyright issues in Generative AI.
- Securing Agentic workflows (Human-in-the-Loop configurations).
- [EU AI Act](https://artificialintelligenceact.eu/) and global compliance.

# 12. Career Development & Strategy
- Building an AI/Agent Portfolio Showcase (e.g., specialized CrewAI workflows, custom RAG apps).
- System Design for LLM Applications.
- MLOps and Infrastructure provisioning.