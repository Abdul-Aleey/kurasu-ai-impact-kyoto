# Kurasu AI — Agent Flow Reference

How a request actually moves through the system for each of the 8 specialist agents, from the
user's first message to the final response. See [`architecture.md`](./architecture.md) for how
these flows sit inside the overall system.

**Legend used across every diagram:**

| Shape / color | Meaning |
|---|---|
| 🟫 Rounded box | User input |
| 🟦 Rectangle | Orchestrator step |
| 🟩 Rectangle | Deterministic / verified compute (never guessed by the model) |
| 🟧 Rectangle | Specialist (LLM) reasoning |
| ⬜ Rectangle | External tool / API call |
| ⬛ Rounded box | Final response |

---

## 🧭 Ask Kurasu

General entry point — the user doesn't need to know which feature fits.

```mermaid
flowchart TD
    U(["User asks a general question,<br/>optionally with location"]) --> O["Orchestrator: minimal required fields,<br/>reaches ready almost immediately"]
    O --> S{"Specialist decides"}
    S -->|"can answer directly"| SE["Google Search,<br/>preferring official/government sources"]
    SE --> R1(["Response: direct answer"])
    S -->|"genuinely ambiguous"| C["Ask exactly ONE<br/>clarifying question"]
    S -->|"clearly matches a feature"| REC(["Response: recommend<br/>the specific existing feature"])

    classDef input fill:#EFEAE0,stroke:#8C8471,color:#3D3826;
    classDef orch fill:#E4E9F0,stroke:#33507D,color:#1E3252;
    classDef llm fill:#F3E3DA,stroke:#B54A26,color:#7A3115;
    classDef ext fill:#E5E7EA,stroke:#5E6773,color:#2B333B;
    classDef resp fill:#1C2333,stroke:#1C2333,color:#F5F1E7;

    class U input
    class O orch
    class S,C llm
    class SE ext
    class R1,REC resp
```

---

## 🏥 Clinic Finder

```mermaid
flowchart TD
    U(["User describes symptoms,<br/>with location"]) --> O["Orchestrator collects<br/>symptoms + location"]
    O --> SE["Google Search:<br/>real nearby clinics/hospitals"]
    SE --> S["Specialist explains fit<br/>in plain English"]
    S --> R(["Response: ranked clinic list<br/>+ map links"])

    classDef input fill:#EFEAE0,stroke:#8C8471,color:#3D3826;
    classDef orch fill:#E4E9F0,stroke:#33507D,color:#1E3252;
    classDef llm fill:#F3E3DA,stroke:#B54A26,color:#7A3115;
    classDef ext fill:#E5E7EA,stroke:#5E6773,color:#2B333B;
    classDef resp fill:#1C2333,stroke:#1C2333,color:#F5F1E7;

    class U input
    class O orch
    class S llm
    class SE ext
    class R resp
```

---

## 🍽️ Restaurant Guide

```mermaid
flowchart TD
    U(["User describes cravings<br/>or dietary needs, with location"]) --> O["Orchestrator collects<br/>craving/diet + location"]
    O --> SE["Google Search:<br/>real nearby restaurants + menus"]
    SE --> S["Specialist translates/explains<br/>menu items and dietary fit"]
    S --> R(["Response: restaurant picks<br/>with why each one fits"])

    classDef input fill:#EFEAE0,stroke:#8C8471,color:#3D3826;
    classDef orch fill:#E4E9F0,stroke:#33507D,color:#1E3252;
    classDef llm fill:#F3E3DA,stroke:#B54A26,color:#7A3115;
    classDef ext fill:#E5E7EA,stroke:#5E6773,color:#2B333B;
    classDef resp fill:#1C2333,stroke:#1C2333,color:#F5F1E7;

    class U input
    class O orch
    class S llm
    class SE ext
    class R resp
```

---

## 🏷️ Ingredient Checker

```mermaid
flowchart TD
    U(["User uploads a product/ingredient photo,<br/>states the concern (halal, vegan, allergy…)"]) --> O["Orchestrator collects<br/>photo + dietary concern"]
    O --> S["Specialist reads the photo directly (vision),<br/>reasons about each ingredient against the concern"]
    S --> R(["Response: safe / not safe / unclear,<br/>with the specific ingredient(s) responsible"])

    classDef input fill:#EFEAE0,stroke:#8C8471,color:#3D3826;
    classDef orch fill:#E4E9F0,stroke:#33507D,color:#1E3252;
    classDef llm fill:#F3E3DA,stroke:#B54A26,color:#7A3115;
    classDef resp fill:#1C2333,stroke:#1C2333,color:#F5F1E7;

    class U input
    class O orch
    class S llm
    class R resp
```

---

## 📦 Delivery Scheduler

The only feature that submits a real request on the user's behalf.

```mermaid
flowchart TD
    U(["User uploads a notice photo/QR<br/>or types a tracking number + time preference"]) --> O["Orchestrator collects<br/>tracking info + time (+ optional date)"]
    O --> D["Deterministic: QR pixel-decoded<br/>directly via OpenCV — never guessed"]
    D --> S{"Specialist: is a decoded<br/>redelivery link present?"}
    S -->|"yes — link alone is sufficient,<br/>no OCR branding needed"| AU["Automation: real headless browser —<br/>opens link → advances to date/time step →<br/>selects time + date → submits"]
    AU --> RES{"Submission<br/>succeeded?"}
    RES -->|"yes"| R1(["Response: genuine<br/>scheduled confirmation"])
    RES -->|"no"| R2(["Response: honest fallback<br/>+ manual steps"])
    S -->|"no confident courier signal"| R2

    classDef input fill:#EFEAE0,stroke:#8C8471,color:#3D3826;
    classDef orch fill:#E4E9F0,stroke:#33507D,color:#1E3252;
    classDef det fill:#E4E9DE,stroke:#566B4C,color:#33402D;
    classDef llm fill:#F3E3DA,stroke:#B54A26,color:#7A3115;
    classDef ext fill:#E5E7EA,stroke:#5E6773,color:#2B333B;
    classDef resp fill:#1C2333,stroke:#1C2333,color:#F5F1E7;

    class U input
    class O orch
    class D det
    class S,RES llm
    class AU ext
    class R1,R2 resp
```

---

## 🆘 Disaster Help

Safety-critical — minimal friction, government data only.

```mermaid
flowchart TD
    U(["User describes an emergency<br/>(or just needs a safe place), with location"]) --> O["Orchestrator: GPS-priority,<br/>never delays on crisis type"]
    O --> D["Deterministic: Haversine nearest-shelter<br/>calc over Japan Gov (GSI) open shelter data"]
    D --> S["Specialist: calm, urgent tone —<br/>safety instruction first, then shelters"]
    S --> R(["Response: nearest outdoor sites<br/>+ indoor shelters, map links, source cited"])

    classDef input fill:#EFEAE0,stroke:#8C8471,color:#3D3826;
    classDef orch fill:#E4E9F0,stroke:#33507D,color:#1E3252;
    classDef det fill:#E4E9DE,stroke:#566B4C,color:#33402D;
    classDef llm fill:#F3E3DA,stroke:#B54A26,color:#7A3115;
    classDef resp fill:#1C2333,stroke:#1C2333,color:#F5F1E7;

    class U input
    class O orch
    class D det
    class S llm
    class R resp
```

---

## 🗑️ Waste Guide

Rules are set per municipality, not nationally — location matters.

```mermaid
flowchart TD
    U(["User asks a waste question,<br/>with location (or names a ward/city directly)"]) --> O["Orchestrator: location optional —<br/>skipped for general questions"]
    O --> D["Deterministic: GPS reverse-geocoded<br/>to an exact ward/city (Nominatim)"]
    D --> S["Specialist searches that exact<br/>municipality's real rules"]
    S --> F{"Reliable info<br/>found?"}
    F -->|"yes"| R1(["Response: concrete categories,<br/>days, bag requirements"])
    F -->|"no"| R2(["Response: says so honestly,<br/>offers general guidance,<br/>suggests Form Decoder & Filler for a local pamphlet"])

    classDef input fill:#EFEAE0,stroke:#8C8471,color:#3D3826;
    classDef orch fill:#E4E9F0,stroke:#33507D,color:#1E3252;
    classDef det fill:#E4E9DE,stroke:#566B4C,color:#33402D;
    classDef llm fill:#F3E3DA,stroke:#B54A26,color:#7A3115;
    classDef resp fill:#1C2333,stroke:#1C2333,color:#F5F1E7;

    class U input
    class O orch
    class D det
    class S,F llm
    class R1,R2 resp
```

---

## 📝 Form Decoder & Filler

The most involved flow — branches into two modes after intent is known, and the "fill" branch
is a real back-and-forth interview before two bilingual images are generated.

```mermaid
flowchart TD
    U(["User uploads 1–5 form photos<br/>(one per page), states decode or fill"]) --> O["Orchestrator collects<br/>photo(s) + explicit intent"]
    O --> B{"Decode<br/>or Fill?"}

    B -->|"DECODE"| DE["Specialist: one-shot explanation<br/>of the form's purpose and every field,<br/>in plain English"]
    DE --> R1(["Response: plain-English explanation —<br/>no file generated"])

    B -->|"FILL"| EX["Deterministic: photo read ONCE —<br/>every field, label, choice-option,<br/>and branching condition identified"]
    EX --> LOOP["Specialist asks the next applicable field —<br/>silently skips any field whose condition isn't met"]
    LOOP -->|"fields remain"| LOOP
    LOOP -->|"all applicable fields answered"| ST["Deterministic: answers structured with<br/>fill-type (write/circle/check/shade) + position"]
    ST --> GEN["Every page × language pair rendered CONCURRENTLY —<br/>AI image-edit model, with a deterministic<br/>overlay fallback per page"]
    GEN --> R2(["Response: completed form,<br/>as real images, in English and Japanese"])

    classDef input fill:#EFEAE0,stroke:#8C8471,color:#3D3826;
    classDef orch fill:#E4E9F0,stroke:#33507D,color:#1E3252;
    classDef det fill:#E4E9DE,stroke:#566B4C,color:#33402D;
    classDef llm fill:#F3E3DA,stroke:#B54A26,color:#7A3115;
    classDef ext fill:#E5E7EA,stroke:#5E6773,color:#2B333B;
    classDef resp fill:#1C2333,stroke:#1C2333,color:#F5F1E7;

    class U input
    class O orch
    class B,LOOP llm
    class EX,ST det
    class DE llm
    class GEN ext
    class R1,R2 resp
```
