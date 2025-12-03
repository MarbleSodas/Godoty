

# **Architectural Blueprint: Production-Grade Agentic Systems with Strands SDK and OpenRouter**

## **1\. Introduction: The Paradigm Shift to Model-Driven Architectures**

The landscape of artificial intelligence application development is undergoing a fundamental transition from rigid, procedural workflows to dynamic, model-driven architectures. This shift is epitomized by the emergence of the "Godoty" project, an application designed to leverage the cognitive flexibility of Large Language Models (LLMs) to execute complex, multi-step tasks. To realize the vision of Godoty, the underlying infrastructure must be engineered with a focus on precision, observability, and persistence. The selection of the **Strands Agents SDK** as the orchestration framework and **OpenRouter** as the model intelligence provider represents a strategic alignment with these modern architectural principles.  
However, the integration of these technologies for a production-grade system requires a departure from standard, tutorial-level implementations. While the Strands SDK offers a simplified interface for defining agents using a "Reason-Act" (ReAct) loop, the abstraction layers that make it accessible can inadvertently obscure the critical telemetry required for business operations. specifically, the precise tracking of token consumption, the calculation of real-time costs across heterogeneous model providers, and the seamless resumption of user sessions with persisted state metrics are not features that function "out of the box" in a naive integration.  
This report serves as an exhaustive architectural guide for the engineering team behind Godoty. It rejects the use of intermediate wrappers such as LiteLLM, which often introduce latency and dependency bloat, in favor of a "close-to-the-metal" integration strategy. By extending the core classes of the Strands SDK—specifically the OpenAIModel and SessionManager components—we establish a high-fidelity control plane. This approach ensures that every computational interaction is accounted for financially and operationally, treating user sessions as enduring, stateful entities that preserve the continuity of both conversation and accumulated metrics.  
The analysis that follows explores the theoretical underpinnings of agentic state and observability, deconstructs the internal mechanisms of the Strands SDK and OpenRouter API, and provides a concrete, implementation-ready blueprint for extending the framework to meet the rigorous requirements of the Godoty application.

### **1.1 The Model-Driven Architecture (MDA) Philosophy**

To understand the architectural decisions recommended in this report, one must first appreciate the design philosophy of the Strands Agents SDK. Unlike traditional workflow engines or graph-based frameworks (such as LangGraph) that require developers to explicitly define state transitions and control flow, Strands adopts a Model-Driven Architecture.1 In this paradigm, the "Agent" is not merely a script that calls an LLM; the Agent is effectively the LLM itself, wrapped in an execution loop that manages the interface between the model's cognitive outputs and the deterministic environment of software tools.  
The Strands SDK manages the "Reason-Act" loop, a cyclical process where the environment's state is fed into the model, which then perceives the context, engages in cognition (reasoning), and decides on an act (tool execution). This cycle repeats until the model determines that the task is complete.3

| Phase | Description | Component Responsibility |
| :---- | :---- | :---- |
| **Environment** | The set of available tools, global context, and conversation history. | strands.Agent |
| **Perception** | The Agent receives the current state (messages \+ tool outputs). | strands.models.model.Model |
| **Cognition** | The Model processes state and emits a "Thought" and "Action". | OpenRouter / LLM |
| **Action** | The SDK executes the selected tool (e.g., Python function). | strands.Agent loop |
| **Observation** | The tool output is fed back into the context for the next cycle. | strands.Agent |

This architectural distinction is critical for metrics tracking because costs and tokens are incurred at *every step* of this loop, not just at the final response. A single user query in Godoty might trigger five internal thought-action cycles, each consuming input and output tokens. A naive implementation that only tracks the final response sent to the user will underreport costs by a significant magnitude—often by a factor of three to five.5 Therefore, the observability mechanism must be embedded deep within the loop itself, capturing the raw telemetry of every intermediate inference call.

### **1.2 The Case for Direct Integration**

The Godoty project specifically requests a solution that avoids the use of LiteLLM or similar wrappers.6 While such wrappers provide a convenient abstraction for standardizing APIs across different providers, they introduce a "lowest common denominator" problem. By abstracting away the specifics of the provider, they often obscure unique features or metadata fields that are essential for advanced monitoring.  
OpenRouter, as an aggregator, provides specific headers for application ranking (HTTP-Referer, X-Title) and specific response fields for cost and usage tracking that standard OpenAI-compatible wrappers might discard or mishandle.7 A direct integration involves subclassing the Strands Model directly and manipulating the underlying openai client to ensure that these specific fields are preserved and propagated to the application layer. This strategy minimizes latency by removing a middleware hop and maximizes control, allowing Godoty to leverage the full specificities of the OpenRouter API without the constraints of a generic wrapper.  
---

## **2\. Infrastructure Analysis: The OpenRouter Ecosystem**

The choice of OpenRouter as the model provider for Godoty introduces specific architectural requirements that differ from a direct connection to a single provider like OpenAI or Anthropic. OpenRouter acts as a unified interface (gateway) to a multitude of models, normalizing their APIs into an OpenAI-compatible format while adding layers of routing, pricing, and analytics.

### **2.1 The Gateway Protocol and Header Management**

OpenRouter sits as an intermediary between the Godoty application and upstream providers (e.g., Anthropic, OpenAI, Meta, Mistral). It exposes an endpoint at https://openrouter.ai/api/v1 that mimics the OpenAI Chat Completions API. However, simply treating it as a standard OpenAI endpoint is insufficient for a production application that aims for high observability and community visibility.  
One of the unique requirements of OpenRouter is the use of specific HTTP headers to identify the calling application. These headers are used to populate the "Apps" leaderboard and provide analytics on the OpenRouter dashboard.9

* **HTTP-Referer**: This header should contain the URL of the Godoty application (e.g., https://godoty.app). It allows OpenRouter to link usage statistics to a verifiable domain.  
* **X-Title**: This header allows the application to declare its name explicitly (e.g., "Godoty Agent").

In a standard Strands implementation using the basic OpenAIModel, these headers are not set by default. The OpenAIModel class accepts a client\_args dictionary, which is passed to the underlying openai.OpenAI or openai.AsyncOpenAI client.7 To satisfy the Godoty requirements, the initialization logic must be intercepted to inject these headers into every request.  
**Table 2.1: Critical OpenRouter Configuration Parameters**

| Parameter | Location | Purpose | Strands Integration Point |
| :---- | :---- | :---- | :---- |
| base\_url | Client Config | Points the SDK to https://openrouter.ai/api/v1 instead of OpenAI. | client\_args in OpenAIModel constructor. |
| api\_key | Client Config | Authenticates the Godoty account. | client\_args in OpenAIModel constructor. |
| HTTP-Referer | HTTP Header | Identifies the app URL for rankings and stats. | default\_headers in client\_args. |
| X-Title | HTTP Header | Identifies the app name for rankings. | default\_headers in client\_args. |
| include\_usage | Request Body | Forces the API to return token counts even in streaming mode. | stream\_options in model params. |

### **2.2 Cost Transparency and Tokenization Challenges**

A significant challenge in using OpenRouter is the heterogeneity of the models. Unlike a single-provider integration where the tokenizer is consistent (e.g., cl100k\_base for OpenAI models), OpenRouter serves models with vastly different tokenization schemes (e.g., Llama 3's tokenizer vs. Claude 3's tokenizer).  
Standard Python libraries for token counting, such as tiktoken, are generally optimized for OpenAI models. Relying on client-side counting for a model like anthropic/claude-3-opus or google/gemini-pro routed through OpenRouter will lead to discrepancies between the "estimated" tokens and the "billed" tokens. These discrepancies can be substantial, leading to inaccurate metrics displayed to the user.12  
Therefore, the architecture must rely strictly on the **server-side reporting** of token usage. OpenRouter (and the underlying OpenAI API spec) supports a feature where the usage statistics are sent as part of the final chunk in a streaming response. Capturing this specific payload is the crux of accurate metrics tracking. The architecture must ensure that the streaming mechanism used by Strands does not swallow this final "usage chunk" but rather extracts it and makes it available to the session manager.13  
Furthermore, OpenRouter provides a "Cost" field in its response headers or usage object (often as x-openrouter-cost or derived from usage fields combined with pricing endpoints). The implementation must be robust enough to look for these OpenRouter-specific extensions to standard OpenAI responses.  
---

## **3\. Dissecting the Strands Agents SDK**

To effectively extend Strands for Godoty's needs, we must first perform a deep dive into its internal class structure. The SDK is designed to be extensible, but modifying its core behavior regarding metrics and state persistence requires precise intervention points.

### **3.1 The Model Abstraction Layer**

The core of the Strands SDK is the abstract base class strands.models.model.Model.14 This class defines the contract that all model providers must fulfill. The most critical method for our purposes is stream().

Python

@abc.abstractmethod  
def stream(  
    self,   
    messages: Messages,   
    tool\_specs: Optional\] \= None,   
    system\_prompt: Optional\[str\] \= None,   
    \*\*kwargs: Any  
) \-\> AsyncGenerator:  
    """Stream conversation with the model."""  
    pass

The stream method is responsible for the full lifecycle of a single inference step: formatting the request, sending it to the provider, and yielding StreamEvent objects. A StreamEvent is typically a dictionary or a typed object containing the text delta, tool calls, or metadata.

### **3.2 The OpenAIModel Implementation**

The concrete implementation strands.models.openai.OpenAIModel wraps the official openai Python library. It translates the Strands Messages format into the OpenAI chat format and calls client.chat.completions.create.11  
Crucially, the default behavior of OpenAIModel in Strands is designed to normalize the output. It iterates over the chunks returned by the OpenAI client and converts them into a standard Strands format. During this conversion, "extra" fields that are not part of the standard text/tool schema—such as OpenRouter's specific cost fields or the usage block at the end of a stream—may be ignored or discarded if the wrapper is not explicitly looking for them.  
Research into the SDK source indications suggests that Strands *does* have logic to look for usage fields in the response.14

Python

\# Pseudo-code logic inferred from Strands SDK patterns  
if "usage" in response or "metrics" in response:  
    yield {"metrics":...}

However, relying on the default implementation assumes that the OpenAIModel knows exactly where OpenRouter places its data. If OpenRouter updates its API or if the openai client version changes how it exposes "extra\_fields," the default wrapper might break or miss data. For a robust, production-grade application like Godoty, we cannot rely on implicit behavior. We must implement a **Hard Override**.

### **3.3 The AgentResult and Metrics Propagation**

When the Agent loop completes, it returns an AgentResult object. This object contains a metrics attribute, which is an instance of EventLoopMetrics.15 This metrics object aggregates data such as:

* accumulated\_usage: A dictionary of total input/output tokens.  
* tool\_metrics: Statistics on tool calls.  
* cycle\_durations: Timing data.

The integrity of AgentResult.metrics is entirely dependent on the Model yielding accurate metrics events during the stream. If our custom model correctly intercepts the OpenRouter usage data and yields it as a StreamEvent, the Agent loop will automatically aggregate it into the final result. This feature of Strands—automatic aggregation of metric events—simplifies our task significantly. We do not need to rewrite the aggregation logic; we only need to ensure the *source* of the data (the Model) is emitting the correct signals.  
---

## **4\. Engineering the Custom Model Provider**

To satisfy the requirement for a "direct solution" that captures all necessary metrics without LiteLLM, we will design a custom class: GodotyOpenRouterModel. This class will inherit from strands.models.openai.OpenAIModel but will override the initialization and streaming logic to ensure OpenRouter compatibility and data capture.

### **4.1 Class Structure and Initialization**

The initialization phase handles the "Connection Protocol." It must accept the OpenRouter API key and configure the openai client to point to the OpenRouter base\_url. It must also inject the required headers.  
Design Pattern: Configuration Injection  
Instead of hardcoding headers inside the class, we should allow them to be passed in, while setting defaults that enforce the Godoty identity.

Python

from strands.models.openai import OpenAIModel

class GodotyOpenRouterModel(OpenAIModel):  
    def \_\_init\_\_(self, api\_key: str, model\_id: str, site\_url: str, app\_name: str):  
        \# Construct the client arguments for the underlying OpenAI client  
        client\_args \= {  
            "api\_key": api\_key,  
            "base\_url": "https://openrouter.ai/api/v1",  
            "default\_headers": {  
                "HTTP-Referer": site\_url,  
                "X-Title": app\_name,  
            }  
        }  
          
        \# Initialize the parent class with the configured client  
        super().\_\_init\_\_(  
            client\_args=client\_args,  
            model\_id=model\_id,  
            \# Critical: This param tells OpenAI/OpenRouter to send usage data  
            params={"stream\_options": {"include\_usage": True}}   
        )

This constructor ensures that every request made by this model is properly routed to OpenRouter with the correct headers, and explicitly requests usage data even for streaming responses.

### **4.2 The Streaming Override and Metrics Interception**

The most complex part of the integration is intercepting the data stream. We need to override the stream method. While we could call super().stream(), doing so delegates the response parsing to Strands. To guarantee we get the raw OpenRouter data, it is safer to wrap the generator and inspect every event.  
OpenRouter sends the usage data in the final chunk of the stream. When include\_usage: True is set, the last chunk will contain a usage field but choices will be empty list \`\`. The standard OpenAI library handles this, but we must ensure Strands' loop sees it.  
The GodotyOpenRouterModel will listen to the stream. When it detects a usage event, it will perform a real-time cost calculation (using a Pricing Service we will define later) and inject a "Cost" metric into the event stream.  
The "Metrics Event" Pattern:  
Strands expects StreamEvent objects. If we yield a dictionary {"metrics": {"usage": {...}, "cost": 0.005}}, the Agent loop will capture this.

### **4.3 Handling the stream\_options Parameter**

A crucial detail often missed in standard integrations is the stream\_options parameter. In the OpenAI API specification (which OpenRouter follows), usage statistics are *not* returned in streaming responses by default. One must explicitly pass stream\_options={"include\_usage": True} in the request body.17  
If this parameter is omitted, the usage field will simply be missing from the final chunk, rendering any downstream tracking logic useless. The GodotyOpenRouterModel enforces this parameter in its \_\_init\_\_ method (as shown above) or by merging it into the kwargs of the stream call.  
---

## **5\. Advanced Metrics and Cost Accounting Architecture**

Tracking tokens is a technical task; tracking *cost* is a business logic task. Because OpenRouter hosts hundreds of models with varying prices (that can change), hardcoding prices into the application is brittle. We propose a "Pricing Oracle" pattern.

### **5.1 The Economics of Token Usage**

In an agentic system, the relationship between input (prompt) tokens and output (completion) tokens is rarely 1:1.

* **Input Tokens:** Usually dominate the cost in RAG (Retrieval Augmented Generation) scenarios where large contexts are loaded.  
* **Output Tokens:** Are typically more expensive (often 3x-10x the price of input tokens) but lower in volume.  
* **Reasoning Tokens:** Some newer models (like OpenAI o1 or reasoning models via OpenRouter) generate "hidden" reasoning tokens that are billed as output tokens but are not visible in the final text. OpenRouter reports these, and our system must account for them.18

### **5.2 The Pricing Oracle Service**

The Godoty backend should include a service responsible for maintaining an up-to-date mapping of Model IDs to their pricing.  
**Mechanism:**

1. **Fetch:** On application startup (or periodically), the service queries https://openrouter.ai/api/v1/models.  
2. **Cache:** The response is cached in memory (or Redis). The structure is a dictionary mapping model\_id to pricing objects (prompt, completion, request, image).  
3. **Calculate:** A method calculate\_cost(model\_id, input, output) returns the USD value.

**Table 5.1: Pricing Data Structure (Conceptual)**

| Field | Source | Description | Usage in Calculation |
| :---- | :---- | :---- | :---- |
| id | API Response | The model slug (e.g., anthropic/claude-3-opus). | Lookup Key. |
| pricing.prompt | API Response | Cost per input token (USD). | input\_tokens \* pricing.prompt |
| pricing.completion | API Response | Cost per output token (USD). | output\_tokens \* pricing.completion |
| pricing.image | API Response | Cost per image processed. | image\_count \* pricing.image |
| pricing.request | API Response | Per-request overhead (rare). | Added to total if \> 0\. |

This service decouples the pricing logic from the model execution logic. The GodotyOpenRouterModel will call this service whenever it receives a usage report.  
---

## **6\. Stateful Session Management and Persistence**

The user requirement to "open up previous session and continue while displaying proper metrics" necessitates a robust persistence strategy. Strands provides a SessionManager interface, but its default implementations are basic. We need to elevate the concept of a session from a "log of messages" to a "stateful container of application history."

### **6.1 The Theory of Session Persistence**

In the context of Strands, a session is defined by three components 19:

1. **Conversation History:** The sequence of UserMessage, AssistantMessage, and ToolMessage objects. This allows the LLM to "remember" what was said.  
2. **Agent State:** A key-value store (dict) attached to the agent. This is where custom variables, memory pointers, and *metrics* reside.  
3. **Session Metadata:** Timestamps, session ID, and user ownership.

Standard session managers (like FileSessionManager) serialize the conversation history effectively. However, they do not inherently track *cumulative* metrics across multiple runs. If a user runs a query, closes the app, and returns, the new Agent instance starts with zero metrics for the *current* run. To display the "Session Total," we must persist the accumulated total in the Agent State.

### **6.2 Data Models for Persistence**

The Strands SDK uses specific data models for serialization:

* **Session**: The top-level container.  
* **SessionAgent**: Represents the agent within the session. Contains the state dictionary.  
* **SessionMessage**: The individual interaction records.

The critical insight here is that SessionAgent.state is automatically serialized and deserialized by the SessionManager. Therefore, we do not need to create a separate database table for "Session Costs." We can store the cost ledger directly inside the agent's state.  
The "Metrics Ledger" Pattern:  
Instead of storing a single number total\_cost, we should store a ledger in agent.state\["godoty\_metrics"\].

JSON

{  
  "total\_cost": 1.25,  
  "total\_tokens": 45000,  
  "run\_history": \[  
    {"timestamp": "...", "model": "gpt-4", "cost": 0.50},  
    {"timestamp": "...", "model": "claude-3", "cost": 0.75}  
  \]  
}

This approach handles "Model Switching" gracefully. If the user switches models halfway through a session, the ledger accurately reflects the mixed pricing history.

### **6.3 Implementing the Persistence Workflow**

The FileSessionManager provided by Strands stores sessions as JSON files on the local filesystem.19 For a production application like Godoty, this might eventually move to a database (Postgres/Redis), but the interface remains the same.  
**The Workflow for "Resuming" a Session:**

1. **Initialization:** The application instantiates a SessionManager with a specific session\_id.  
2. **Agent Creation:** The Agent is initialized with this manager.  
   Python  
   session\_manager \= FileSessionManager(session\_id="user-session-123")  
   agent \= Agent(model=model, session\_manager=session\_manager)

3. **Automatic Rehydration:** The Agent constructor calls session\_manager.read\_agent(). It loads the state dictionary from the JSON file.  
4. **UI Display:** Before the user even types a message, the application inspects agent.state.get("godoty\_metrics"). It uses this data to render the "Total Cost: $1.25" badge on the frontend.  
5. **Execution:** When the user sends a new message, the Agent runs.  
6. **Update:** Upon completion, the application calculates the cost of the *new* run, adds it to the total\_cost in agent.state, and the SessionManager automatically saves the updated state back to the disk (or DB).

This workflow ensures that the metrics are durable. They survive application restarts and server crashes because they are committed to storage alongside the conversation history.  
---

## **7\. Implementation: The Direct Solution Guide**

This section synthesizes the architectural analysis into a concrete implementation guide. This code avoids LiteLLM and uses the native Strands interfaces.

### **7.1 Component 1: The Pricing Service (core/pricing.py)**

This module handles the economic logic.

Python

import requests  
from functools import lru\_cache  
from typing import Dict, Any

class PricingService:  
    \_pricing\_cache: Dict\[str, Any\] \= {}

    @classmethod  
    def load\_pricing(cls):  
        """Fetches latest pricing from OpenRouter."""  
        try:  
            response \= requests.get("https://openrouter.ai/api/v1/models")  
            response.raise\_for\_status()  
            data \= response.json()\["data"\]  
            for model in data:  
                cls.\_pricing\_cache\[model\["id"\]\] \= {  
                    "prompt": float(model\["pricing"\]\["prompt"\]),  
                    "completion": float(model\["pricing"\]\["completion"\])  
                }  
        except Exception as e:  
            \# Fallback or log error  
            print(f"Failed to load pricing: {e}")

    @classmethod  
    def calculate\_cost(cls, model\_id: str, input\_tokens: int, output\_tokens: int) \-\> float:  
        if not cls.\_pricing\_cache:  
            cls.load\_pricing()  
          
        pricing \= cls.\_pricing\_cache.get(model\_id)  
        if not pricing:  
            return 0.0  
              
        \# Pricing is typically per 1 token or per 1M tokens depending on API.  
        \# OpenRouter API returns price \*per token\* usually, but verify normalization.  
        \# Assuming price is per-token (standardized by OpenRouter API to avoid 1M math errors):  
        cost \= (input\_tokens \* pricing\["prompt"\]) \+ (output\_tokens \* pricing\["completion"\])  
        return cost

### **7.2 Component 2: The Custom Model (core/model.py)**

This module extends the Strands OpenAIModel.

Python

from typing import Any, AsyncGenerator, Optional, List  
from strands.models.openai import OpenAIModel  
from strands.types.streaming import StreamEvent  
from strands.types.content import Messages  
from core.pricing import PricingService

class GodotyOpenRouterModel(OpenAIModel):  
    def \_\_init\_\_(self, api\_key: str, model\_id: str, site\_url: str, app\_name: str):  
        super().\_\_init\_\_(  
            client\_args={  
                "api\_key": api\_key,  
                "base\_url": "https://openrouter.ai/api/v1",  
                "default\_headers": {  
                    "HTTP-Referer": site\_url,  
                    "X-Title": app\_name,  
                }  
            },  
            model\_id=model\_id,  
            \# Force usage reporting  
            params={"stream\_options": {"include\_usage": True}}  
        )

    async def stream(  
        self,  
        messages: Messages,  
        \*\*kwargs: Any,  
    ) \-\> AsyncGenerator:  
          
        \# We wrap the parent stream to inspect events  
        async for event in super().stream(messages, \*\*kwargs):  
            yield event  
              
            \# Check for metrics event  
            \# Note: Strands SDK structure puts usage in "metrics" key of the event  
            if "metrics" in event:  
                usage \= event\["metrics"\].get("usage", {})  
                if usage:  
                    input\_tok \= usage.get("prompt\_tokens", 0\)  
                    output\_tok \= usage.get("completion\_tokens", 0\)  
                      
                    \# Calculate Cost  
                    cost \= PricingService.calculate\_cost(  
                        self.model\_id, input\_tok, output\_tok  
                    )  
                      
                    \# Inject Cost into the event  
                    \# We mutate the dictionary to bubble up the cost  
                    event\["metrics"\]\["godoty\_cost"\] \= cost

### **7.3 Component 3: The Main Application Loop (app.py)**

This component ties everything together, handling session resumption and persistence.

Python

import asyncio  
import os  
from strands import Agent  
from strands.session.file\_session\_manager import FileSessionManager  
from core.model import GodotyOpenRouterModel

async def run\_godoty\_session(session\_id: str, user\_query: str):  
    \# 1\. Setup Infrastructure  
    \# Using FileSessionManager for persistence (saves to./sessions/{session\_id}/agent.json)  
    session\_manager \= FileSessionManager(session\_id=session\_id)  
      
    \# Initialize our custom model  
    model \= GodotyOpenRouterModel(  
        api\_key=os.environ.get("OPENROUTER\_API\_KEY"),  
        model\_id="anthropic/claude-3.5-sonnet",  
        site\_url="https://godoty.app",  
        app\_name="Godoty"  
    )

    \# 2\. Rehydrate Agent  
    \# If session exists, this loads conversation history AND 'state'  
    agent \= Agent(  
        model=model,  
        session\_manager=session\_manager,  
        system\_prompt="You are Godoty, an advanced AI assistant."  
    )

    \# 3\. "Open up previous session" \- Display Metrics  
    \# We read from the rehydrated state  
    metrics\_state \= agent.state.get("godoty\_metrics", {"total\_cost": 0.0, "total\_tokens": 0})  
    print(f"--- Session: {session\_id} \---")  
    print(f"Previous Cost: ${metrics\_state\['total\_cost'\]:.4f}")  
    print(f"Previous Tokens: {metrics\_state\['total\_tokens'\]}")

    \# 4\. Execute the Interaction  
    \# The agent uses the model to reason and act.  
    print(f"User: {user\_query}")  
    result \= await agent.run\_async(user\_query)

    \# 5\. Extract and Accumulate Metrics  
    \# The result.metrics contains the aggregated usage from the run  
    \# Because our Model injected 'godoty\_cost', we check if it bubbled up,  
    \# or we recalculate it here for safety.  
      
    run\_usage \= result.metrics.accumulated\_usage  
    run\_tokens \= run\_usage.get("totalTokens", 0\)  
      
    \# Recalculate cost for this specific run to be precise  
    run\_cost \= PricingService.calculate\_cost(  
        model.model\_id,   
        run\_usage.get("promptTokens", 0),   
        run\_usage.get("completionTokens", 0\)  
    )

    \# 6\. Update Persistent State  
    metrics\_state\["total\_cost"\] \+= run\_cost  
    metrics\_state\["total\_tokens"\] \+= run\_tokens  
      
    \# Save back to agent state  
    agent.state\["godoty\_metrics"\] \= metrics\_state  
      
    \# Explicitly trigger a save (Strands usually saves on turn end, but explicit is safer)  
    session\_manager.update\_agent(session\_id, agent.to\_session\_agent())

    print(f"Response: {result.response}")  
    print(f"Run Cost: ${run\_cost:.4f}")  
    print(f"New Session Total: ${metrics\_state\['total\_cost'\]:.4f}")

if \_\_name\_\_ \== "\_\_main\_\_":  
    \# Example usage  
    asyncio.run(run\_godoty\_session("user-123", "Write a Python script to parse CSV."))

---

## **8\. Observability and Production Readiness**

While the code above handles the functional requirements of cost and session management, a production system requires broader observability.

### **8.1 Beyond Cost: Latency and Reliability**

OpenRouter aggregates many providers. Occasionally, a specific provider (e.g., "Anthropic via Cloudflare") may experience latency or downtime.

* **Latency Tracking:** The AgentResult.metrics object includes cycle\_durations. Godoty should log this. If cycle\_durations spikes, it indicates network issues with OpenRouter.  
* **Provider Routing:** OpenRouter allows "fallback" routing (e.g., "Try Claude, if down, try GPT-4"). If fallbacks are configured, the model\_id might change *during* a request. The GodotyOpenRouterModel should ideally inspect the model field in the response chunk to confirm *which* model actually served the request, ensuring accurate pricing.

### **8.2 OpenTelemetry (OTEL) Integration**

The Strands SDK has native support for OpenTelemetry.20 While the user requested a "direct" solution (implying custom coding), for a large-scale deployment, integrating OTEL is the industry standard for tracing.

* **Trace Context:** Strands propagates trace IDs through the Agent loop.  
* **Integration:** Godoty can install strands-agents\[otel\] and configure an exporter (like Jaeger or Honeycomb). This provides a visual timeline of the ReAct loop: Input \-\> Thought \-\> Tool Call \-\> Output. This is complementary to the custom cost tracking developed in this report.

### **8.3 Security Considerations**

The OpenRouterModel requires an API key.

* **Key Management:** Never hardcode the key. Use os.getenv("OPENROUTER\_API\_KEY").  
* **Client-Side Exposure:** Ensure that the godoty\_metrics state is sanitized before being sent to a frontend client. While cost is not sensitive, other parts of the agent state might be.

---

## **9\. Conclusion**

The architecture detailed in this report provides the Godoty project with a robust, scalable, and fully observable foundation. By bypassing generic wrappers like LiteLLM and instead extending the native OpenAIModel class of the Strands Agents SDK, we achieve a direct integration that is highly responsive to the specific capabilities of OpenRouter.  
Key architectural achievements of this design include:

1. **Direct Control:** The custom GodotyOpenRouterModel allows for precise injection of headers (HTTP-Referer, X-Title) required for OpenRouter ecosystem participation.  
2. **Granular Observability:** By enforcing stream\_options={"include\_usage": True} and intercepting the event stream, we guarantee that every token is counted and priced, regardless of the underlying model's tokenizer.  
3. **Stateful Continuity:** Leveraging the SessionManager to persist a cumulative "Metrics Ledger" within the Agent State ensures that users can resume sessions seamlessly with full context and accurate financial history.

This blueprint transforms the Strands SDK from a tool for simple experimentation into a production-grade engine capable of powering the complex, stateful, and metered interactions required by the Godoty application.

#### **Works cited**

1. Introducing Strands Agents, an Open Source AI Agents SDK \- AWS, accessed November 26, 2025, [https://aws.amazon.com/blogs/opensource/introducing-strands-agents-an-open-source-ai-agents-sdk/](https://aws.amazon.com/blogs/opensource/introducing-strands-agents-an-open-source-ai-agents-sdk/)  
2. Introducing Strands Agents 1.0: Production-Ready Multi-Agent Orchestration Made Simple, accessed November 26, 2025, [https://aws.amazon.com/blogs/opensource/introducing-strands-agents-1-0-production-ready-multi-agent-orchestration-made-simple/](https://aws.amazon.com/blogs/opensource/introducing-strands-agents-1-0-production-ready-multi-agent-orchestration-made-simple/)  
3. Introducing AWS Strands Agents: A New Paradigm in AI Agent Development, accessed November 26, 2025, [https://garystafford.medium.com/introducing-aws-strands-agents-a-new-paradigm-in-ai-agent-development-1d7c99588315](https://garystafford.medium.com/introducing-aws-strands-agents-a-new-paradigm-in-ai-agent-development-1d7c99588315)  
4. Strands Agents SDK: A technical deep dive into agent architectures and observability \- AWS, accessed November 26, 2025, [https://aws.amazon.com/blogs/machine-learning/strands-agents-sdk-a-technical-deep-dive-into-agent-architectures-and-observability/](https://aws.amazon.com/blogs/machine-learning/strands-agents-sdk-a-technical-deep-dive-into-agent-architectures-and-observability/)  
5. Strands Agents \- Agentic Runtime Search with Hybrid Retrieval | AWS Builder Center, accessed November 26, 2025, [https://builder.aws.com/content/31KB6Tx7NhXkhCcOTi7rh2TDhe2/strands-agents-agentic-runtime-search-with-hybrid-retrieval](https://builder.aws.com/content/31KB6Tx7NhXkhCcOTi7rh2TDhe2/strands-agents-agentic-runtime-search-with-hybrid-retrieval)  
6. What framework are you using to build AI Agents? : r/LocalLLaMA \- Reddit, accessed November 26, 2025, [https://www.reddit.com/r/LocalLLaMA/comments/1lmni3q/what\_framework\_are\_you\_using\_to\_build\_ai\_agents/](https://www.reddit.com/r/LocalLLaMA/comments/1lmni3q/what_framework_are_you_using_to_build_ai_agents/)  
7. Strands Agents \- Portkey Docs, accessed November 26, 2025, [https://portkey.ai/docs/integrations/agents/strands](https://portkey.ai/docs/integrations/agents/strands)  
8. Vercel AI Gateway Integration \- Langfuse, accessed November 26, 2025, [https://langfuse.com/integrations/gateways/vercel-ai-gateway](https://langfuse.com/integrations/gateways/vercel-ai-gateway)  
9. OpenRouter Quickstart Guide | Developer Documentation, accessed November 26, 2025, [https://openrouter.ai/docs/quickstart](https://openrouter.ai/docs/quickstart)  
10. Access and Use Auto Router via OpenRouter using API Key \- TypingMind, accessed November 26, 2025, [https://www.typingmind.com/guide/openrouter/auto](https://www.typingmind.com/guide/openrouter/auto)  
11. OpenAI \- Strands Agents, accessed November 26, 2025, [https://strandsagents.com/latest/documentation/docs/user-guide/concepts/model-providers/openai/](https://strandsagents.com/latest/documentation/docs/user-guide/concepts/model-providers/openai/)  
12. OpenRouter API Reference | Complete API Documentation, accessed November 26, 2025, [https://openrouter.ai/docs/api-reference/api-reference/overview](https://openrouter.ai/docs/api-reference/api-reference/overview)  
13. Usage Accounting | Track AI Model Usage with OpenRouter, accessed November 26, 2025, [https://openrouter.ai/docs/use-cases/usage-accounting](https://openrouter.ai/docs/use-cases/usage-accounting)  
14. Models \- Strands Agents, accessed November 26, 2025, [https://strandsagents.com/latest/documentation/docs/api-reference/models/](https://strandsagents.com/latest/documentation/docs/api-reference/models/)  
15. Metrics \- Strands Agents, accessed November 26, 2025, [https://strandsagents.com/latest/documentation/docs/user-guide/observability-evaluation/metrics/](https://strandsagents.com/latest/documentation/docs/user-guide/observability-evaluation/metrics/)  
16. Introducing AWS Strands Agents: A New Paradigm in AI Agent Development, accessed November 26, 2025, [https://builder.aws.com/content/2xhr9isUtaO3STZPwdvj6tsttIl/introducing-aws-strands-agents-a-new-paradigm-in-ai-agent-development](https://builder.aws.com/content/2xhr9isUtaO3STZPwdvj6tsttIl/introducing-aws-strands-agents-a-new-paradigm-in-ai-agent-development)  
17. \[FEATURE\] Support a fixed, injected \`AsyncOpenAI\` client to enable alternative interface-compatible clients · Issue \#1103 · strands-agents/sdk-python \- GitHub, accessed November 26, 2025, [https://github.com/strands-agents/sdk-python/issues/1103](https://github.com/strands-agents/sdk-python/issues/1103)  
18. OpenRouter: A Guide With Practical Examples \- DataCamp, accessed November 26, 2025, [https://www.datacamp.com/tutorial/openrouter](https://www.datacamp.com/tutorial/openrouter)  
19. Session Management \- Strands Agents, accessed November 26, 2025, [https://strandsagents.com/latest/documentation/docs/user-guide/concepts/agents/session-management/](https://strandsagents.com/latest/documentation/docs/user-guide/concepts/agents/session-management/)  
20. Integrate Langfuse with the Strands Agents SDK, accessed November 26, 2025, [https://langfuse.com/integrations/frameworks/strands-agents](https://langfuse.com/integrations/frameworks/strands-agents)  
21. Strands Agents Instrumentation \- LangWatch, accessed November 26, 2025, [https://docs.langwatch.ai/integration/python/integrations/strand-agents](https://docs.langwatch.ai/integration/python/integrations/strand-agents)