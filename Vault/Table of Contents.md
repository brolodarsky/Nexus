---
aliases: [TOC, Index, Map of Content]
tags: [index, master]
type: overview
---
# 1. The Core: Identity & Governance
_Systemic foundations for mental clarity, resilience, and long-term vision._
## 1.1. Philosophy & Personal North Star
- **Principles & Ethics:** Core values and decision-making frameworks.
- **The 10-Year Horizon:** Strategic goals for the 30s, 40s, and beyond.
- **Legacy & Impact:** What do I want to build that lasts?
- **[[Current Learning]]:** Active focus and active subjects.
- **[[Shit To Do]]
## 1.2. Personal Knowledge Management (PKM)
- **Brain 2.0 Meta:** How I tag, link, and maintain this system.
- **[[Protocol - System Maintenance]]**
- **[[Protocol - Laptop App List Update]]**
- **[[Protocol - Monthly Hard Drive Backup]]**
- **[[Protocol - New Note Template]]**
- **Toolbox:** Documentation for the Pixel 8 Pro, Obsidian/Logseq workflows, and local LLM setups.
## 1.3. Security & Digital Sovereignty
- **Security Audit:** Password management strategy, 2FA recovery locations, and encryption protocols.
- **Digital Inheritance:** Instructions for account access in case of emergency.
## 1.4. Emergency & Survival
- **Emergency Contacts:** Medical, family, and local services.
- **Crisis Protocols:** What to do in medical or financial emergencies.
- **Vehicle Prep:** Emergency kit inventory for the 2005 Honda Pilot.
# 2. Health
## 2.1. Fitness
- **Cardiovascular Base:** Running/Cycling logs and endurance strategies.
- **Strength & Mobility:** Long-term joint health and maintenance.
- **Performance Media:** YouTube playlists for cardio motivation/form tutorials.
## 2.2. Medical
- **Health Logs:** History of illnesses, injuries, and surgeries.
- **Lab Work & Biomarkers:** Tracking bloodwork, Vitamin D levels, etc., over years.
- **Vaccination & Screening:** Long-term preventative maintenance records.
- **Sleep Hygiene:** Protocols for deep rest and circadian rhythm alignment.
## 2.3. Psych
- **Cognitive Load Management:** Tools for balancing caregiving, technical work, and social life.
- **Meditation & Mindfulness:** Rituals for grounding and focus.
- **Stress Mitigation:** Systems for decompressing after high-output days.
- **CBT**
- **ACT**
## 2.4. Nutrition
- **The Recipe Vault:** High-protein/low-calorie favorites (Crack Slaw, etc.).    
- **Feeding Reference:** Bookmarks/Videos on nutrition science and food prep.
# 3. Forge
Technical Mastery
## 3.1. Projects 
The Lab
- **[[Project Maturity Checklist]]:** Standardized checklist for enterprise-grade applications.
- [Brain 2](https://github.com/brolodarsky/Brain2)
- **[Project Feeder](https://github.com/brolodarsky/Feeder):** Python logic, UI/UX, and database development.
- **[Project MEM Billing](<file:///C:\Users\Willi\Documents\Projects\MEMBilling>):** Billing Automation. Scripts for LCSW medical billing efficiency.
- **Project - Domain Portfolio:** Management and monetization of SiliSlick.com and others.
### 3.1.2. Script Attic
- Inactive tools, experiments, and one-off Python scripts.
## 3.2. Library & Learning
- **Technical Archive:** Engineering-specific YouTube tutorials, GitHub repos, and research papers.
- **[[AI Agents]] | LLMs | Vector Search | Robotics:** (Original technical deep-dives).
### 3.2.1. Foundational Mathematics & Statistics
[LibreTexts Mathematics](https://math.libretexts.org/)
#### Linear Algebra
##### Core Concepts:
- [[Overview - Linear Algebra]]
	- Vectors, matrices, and matrix operations 
		- ([Khan Academy: Vectors and spaces](https://www.khanacademy.org/math/linear-algebra/vectors-and-spaces))
	- Linear transformations, Systems of linear equations
	- Dot products, cross products
##### Advanced Topics for AI:
- Eigenvalues and eigenvectors ([3Blue1Brown: Eigenvectors and eigenvalues](https://www.youtube.com/watch?v=PFDu9oVAE-g&list=PLZHQObOWTQDPD3MizzM2xVFitgF8hE_ab&index=14))
- Singular Value Decomposition (SVD) ([Stanford CS229: SVD Review](https://cs229.stanford.edu/section/cs229-svd.pdf))
- Principal Component Analysis (PCA) ([StatQuest: PCA explained](https://www.youtube.com/watch?v=FgakZw6K1QQ))
- Tensors and tensor operations (especially for Deep Learning) ([TensorFlow: Introduction to Tensors](https://www.tensorflow.org/guide/tensor))
##### Where to Learn:
- [Essence of Linear Algebra (YouTube - 3Blue1Brown)](https://www.youtube.com/playlist?list=PLZHQObOWTQDPD3MizzM2xVFitgF8hE_ab) - Highly intuitive visual explanations.
- [Khan Academy: Linear Algebra](https://www.khanacademy.org/math/linear-algebra)
- [Mathematics for Machine Learning Specialization (Coursera)](https://www.coursera.org/specializations/mathematics-machine-learning)

#### Probability & Statistics
Resources:
	[NIST/SEMATECH e-Handbook of Statistical Methods](https://www.itl.nist.gov/div898/handbook/index.htm)
##### Core Concepts:
#### Descriptive statistics & Probability theory
- Mean, Median, Mode, Variance, Standard Deviation
- Sample spaces, conditional probability
- Bayes’ Theorem ([3Blue1Brown](https://www.youtube.com/watch?v=HZGCoVF3YvM))
#### [[Probability Distributions]]
- Normal, Poisson, Binomial, Uniform
##### Advanced Topics for AI:
- Hypothesis testing & p-values, confidence intervals
- Regression analysis (Linear, Logistic - covered further in ML)
- Markov Chains, Hidden Markov Models (HMMs) - (Core for classical NLP)
- Information Theory: Entropy, Mutual Information, KL Divergence ([Visual Information Theory](https://colah.github.io/posts/2015-09-Visual-Information/))

#### Calculus & Optimization
##### Core Concepts:
- [[Calculus Overview]]
- [[Differentiation & Partial Derivatives]]
- Integrals and Multivariable calculus
##### Optimization Techniques for AI:
- [Gradient Descent](https://www.youtube.com/watch?v=IHZwWFHWa-w) (StatQuest) and its variants (SGD, Adam, etc.)
- Loss functions, cost functions
- Convex optimization
### 3.2.2. Programming & Software Engineering
#### Core Programming Languages
##### [[Python]]
The dominant language for AI/ML and Agentic Workflows.
- Fundamentals: Data types, loops, classes, async/await (crucial for API calls).
- Key Libraries for AI:
- [[NumPy]] : Numerical computing, N-dimensional arrays.
- [Pandas](https://pandas.pydata.org/docs/user_guide/10min.html): Data manipulation.
- [Scikit-learn](https://scikit-learn.org/stable/user_guide.html): Core machine learning library.
- [PyTorch](https://pytorch.org/tutorials/): Deep learning frameworks.
- Requests / AIOHTTP / Pydantic: Crucial for building and interacting with Agent APIs.

##### Web Technologies (For Browser Agents)
- DOM (Document Object Model) manipulation.
- HTML/CSS structures (XPath, CSS Selectors) for agent web scraping.
- JavaScript basics for understanding client-side rendering.

##### Other Languages
- **C++**: Critical for performance-intensive AI (CUDA kernels, physics simulations).
- **TypeScript**: Increasingly popular for Agent frameworks (LangChain.js, specialized desktop apps).
- **SQL / Shell Scripting (Bash)**: Essential for data pulling and CLI integrations.

#### Software Engineering Practices
- **[[Project Maturity Checklist]]:** Standardized checklist for enterprise-grade applications.
- Version Control (Git) and CI/CD (GitHub Actions)
- Testing: `pytest`, mocking API calls (crucial for testing LLM outputs).
- API Design: RESTful principles, GraphQL, OpenAPI/Swagger specifications (how LLMs read APIs).

### 3.2.3. Machine Learning Fundamentals
[Machine Learning Glossary]([Supervised Learning](https://developers.google.com/machine-learning/glossary#supervised-learning))
#### Types of Learning
- [[Supervised Learning]]: Learning from labeled data (Classification & Regression).
- [Unsupervised Learning](https://developers.google.com/machine-learning/glossary#unsupervised-learning): Clustering (K-Means), Dimensionality Reduction (PCA).
- Reinforcement Learning: Reward-based learning in environments.
- Self-Supervised Learning: (The foundation of modern LLMs).

#### Model Evaluation & Metrics
- Train-validation-test split, Cross-Validation.
- Metrics: Accuracy, Precision, Recall, F1-score, MSE.
- [Bias-Variance Tradeoff](https://en.wikipedia.org/wiki/Bias%E2%80%93variance_tradeoff), Overfitting/Underfitting. Regularization techniques (L1, L2).

#### Common Machine Learning Algorithms
- Linear & Logistic Regression
- Tree-Based Models: Decision Trees, Random Forests, Gradient Boosting (XGBoost).
- SVMs, K-Nearest Neighbors (KNN).

### 3.2.4. Deep Learning (DL)
#### Neural Network Fundamentals
- Neurons, Layers, Activation Functions (Sigmoid, ReLU, GELU).
- Forward Propagation & Backpropagation.
- Optimizers (Adam, RMSprop) and Loss Functions (Cross-Entropy).

#### Deep Learning Architectures
- **CNNs (Convolutional Neural Networks):** Image and video processing (ResNet, YOLO).
- **RNNs & LSTMs:** Sequential data processing (legacy NLP).
- **Transformers:** The definitive architecture for modern AI (Self-Attention mechanism). 
  - [The Illustrated Transformer (Jay Alammar)](http://jalammar.github.io/illustrated-transformer/)

#### Generative AI Advanced Concepts
- **Large Language Models (LLMs):** Pre-training vs. Instruction Fine-Tuning vs. RLHF.
- **Diffusion Models:** Image and video generation (Stable Diffusion, Midjourney, Sora).
- **Multi-Modal Models:** Vision-Language Models (VLMs) like GPT-4o, Claude 3.5 Sonnet.

### 3.2.5. Natural Language Processing (NLP) & Vector Search
#### Core NLP & Embeddings
- Text Representation: Word2Vec, Contextual Embeddings.
- Vector Embeddings: Dense representations of text.
- [[Vector Databases]]: ChromaDB, Pinecone, [Milvus](https://milvus.io/intro), Qdrant. 
- Chunking strategies for parsing large documents.

#### Post-Training & Application
- **[[Prompt Engineering]]:** System prompts, few-shot prompting, prompt injection defenses.
- **[[Retrieval Augmented Generation (RAG)]]:** Connecting LLMs to external data via Vector DBs.
  - Advanced RAG: Semantic routing, query rewriting, re-ranking (Cohere).
- Fine-Tuning: LoRA, QLoRA, Parameter-Efficient Fine-Tuning (PEFT).

### 3.2.6. Intelligent Agents & Autonomy
#### [[AI Agents]]
##### Modern LLM-Based Agents
- Core Architectures: ReAct (Reason + Act), Plan-and-Solve, Reflexion, Chain of Thought (CoT).
- Memory Systems: Short-term (context window) vs. Long-term (Vector DBs).
- Agent Personalities & System Prompts: Directing autonomous behavior safely.

##### Agent Tool Use & Integration (The "Hands")
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

##### Agent Frameworks & Platforms
- **Orchestration:** [LangChain](https://python.langchain.com/), [LlamaIndex](https://www.llamaindex.ai/) (Best for RAG).
- **Multi-Agent Systems:** [CrewAI](https://www.crewai.com/), [Microsoft AutoGen](https://microsoft.github.io/autogen/), [OpenAI Swarm](https://github.com/openai/swarm).
- **Autonomous Coding Agents:** [OpenHands (formerly OpenDevin)](https://github.com/All-Hands-AI/OpenHands), Open Interpreter, Devin/Devika, Cline/Antigravity.
- **Tool Protocols:** [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) (Standardizing tool access for models).

##### Evaluation & Safety for Agents
- Guardrails and bounds (e.g., restricting file paths, enforcing API limits).
- Benchmarking: SWE-bench (coding), WebArena (browser use).
- Preventing prompt injection and unauthorized actions.

### 3.2.7. Data Processing, Engineering & MLOps
#### Data Collection & Pipelines
- Web scraping (BeautifulSoup, Scrapy), API ingestion.
- Data Storage: SQL vs NoSQL, Data Lakes, Data Warehouses.
- Feature Engineering: Normalization, encoding, handling missing data.
#### MLOps (Machine Learning Operations) & Deployment
- Model deployment, serving architectures (vLLM, Ollama for local LLMs).
- Containerization: Docker, Kubernetes.
- Cloud AI: AWS Bedrock, GCP Vertex AI, Azure OpenAI.
- Monitoring: Tracking token usage, latency, and LLM hallucinations (LangSmith, Helicone).

### 3.2.8. Computer Vision (CV)
#### Core Concepts
- Image Preprocessing: OpenCV, Filtering, transformations.
- Object Detection: YOLO, SSD.
- Image Segmentation: Semantic vs. Instance.
- 3D Computer Vision: Point clouds, SLAM (Visual localization).
- Vision Transformers (ViT) and cross-modal implementations.

### 3.2.9. Reinforcement Learning (RL)
#### Core Concepts
- Markov Decision Processes (MDPs), value & policy iteration.
- Algorithms: Q-Learning, Policy Gradients, PPO (Proximal Policy Optimization).
- Deep Reinforcement Learning (DRL).
- RLHF (Reinforcement Learning from Human Feedback) & RLAIF (from AI Feedback).

### 3.2.10. Robotics (Hardware & Control Systems)
#### Kinematics, Dynamics & Control
- Forward/Inverse Kinematics.
- PID controllers, State-space representation, Model Predictive Control (MPC).
#### Sensors, Actuators & ROS
- Cameras, LiDAR, IMUs. Motor controllers.
- Robot Operating System ([ROS 2](https://docs.ros.org/en/rolling/)). Nodes, Topics, Messages.
- Simulation: Gazebo, NVIDIA Isaac Sim, MuJoCo.
### 3.2.11. AI Ethics, Safety & Governance

- **Explainable AI (XAI):** Interpretability tools (LIME, SHAP).
- **Safety Guardrails:** Securing agentic workflows and prompt injection defense.
- **Regulation:** Tracking the EU AI Act and global compliance.
### 3.2.12. Career
# 4. Operations & Wealth

_Financial and logistical systems to support a life of freedom._ The "Engine"
## 4.1. Wealth & Asset Management
- [[The Bogle Heads]]
- **Investment Strategy:** Long-term holdings and risk management.
- **Banking & Credit:** Tracking credit scores, loan statuses, and account maintenance.
- **Insurance:** Policies for health, car (Honda Pilot), and professional liability.
- **Digital Assets:** Domain portfolio valuation and strategy.
## 4.2. Infrastructure & Logistics
- **The Home Lab:** Hardware inventory, server setups, and network security.
### 4.2.1. Home Improvement & Maintenance
- **Household Ops:** Recurring tasks for living spaces.
- **[[Project Ideas]]:** Renovation ideas, furniture builds, and aesthetic upgrades.
- **Tool Library:** Inventory of physical tools (drills, saws, etc.) and maintenance guides.
- **Materials & Suppliers:** Local Fort Lee hardware stores and cost tracking.
### 4.2.2. Family & Care
- **Family Estate:** Inventory and liquidation strategy for family assets (Gold/Silver).
- **Parental Care:** Health records, medical billing history, and local Fort Lee resources.
	- [[Plan - Recover & Transition for MEM Practice]]
### 4.2.3. Auto
- **[[Car Info]]:** Persistent vehicle specifications and details.
- **[[Maintenance Log]]:** Service history and recurring tasks for the Pilot.
- **[[Project - Maintenance Tracker Game Plan]]:** Project outline for building an automated Google Sheet tracker.
- **[[Project - Exterior Repair Game Plan]]:** Repair strategy for the driver-side rear quarter panel.
- **[[Project - Blower Motor Noise Fix]]:** Step-by-step guide for resolving HVAC fan noise.
## 4.3. Career Strategy & Revenue
- **[[Employer Skill Requirements]]:** Aggregated "desired background and skills" from job descriptions and market research.
- **Professional Portfolio:** Documentation of AI Rating and Billing experience.
- **The Pivot:** Preparation for AI/Robotics roles (Interview prep, Networking).
- **Resume & Artifacts:** Version control for your professional bio and CV.
- **Professional CRM:** Tracking contacts, mentors, and recruiters in the AI/Robotics industry.
# 5. Playground
_Dedicated space for exploration, relationships, and pure interest._ Connection & Joy
## 5.1. Social Life & Community
- **Family Data**
- **"People Data":** Things people tell me—birthdays, preferences, and important context.
- **Gift Ideas:** Running list of potential gifts for friends and family.
- **Social Club:** Event planning and community building.
- **[[Activities List]]**: Hobbies, sports, or experiences I want to try.
- **Adventure Log:** Places to visit.    
## 5.2. Romance & Partnership
- **Values Alignment:** What am I looking for in a partner?
- **Relationship Maintenance:** Strategies for connection and conflict resolution.
- **Date Ideas:** Local & travel-based.
## 5.3. Culture & Inspiration
- **Media Vault:** Analysis of _The Sopranos_, film, and literature.
- **Music**
- **Reading List:** Books I want to read vs. books finished.
- **[[Education List]]:** Curated paths for World History, Philosophy, and Natural Sciences.
- **[[Movie List]]:** Movies I want to watch vs. movies watched.
- **Writing**
## 5.4. Creativity
- [[Jokes]]
# 6. Capture & Archive
_High-frequency tracking and unsorted information storage. The Memory Bank_
## 6.1. Brain Dump & Inbox
- **[[Quick Capture]]:** Temporary scratchpad for thoughts to be sorted later.
- **Memories Log:** Significant life events, funny moments, and personal milestones.
- **The Trophy Case:** Screenshots of wins, kind words from others, and completed major projects.
## 6.2. The Content Log (General)
- **The YouTube "Everything Else" List:** Funny videos, travel vlogs, and miscellaneous likes.
- **Article & Web Archive:** Random interesting links that don't fit a specific category yet.
## 6.3. Digital Inventory
- **App Audit:** Current apps installed on devices.
	- Pixel 8 Pro
	- [[Laptop App List]].
- **Software Subscriptions:** Tracking costs and renewal dates.
- **Hardware Inventory:** Serial numbers and warranty info.