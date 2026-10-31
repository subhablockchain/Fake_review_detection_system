# 🔬 Research: Fake Review Detection System

## 1. Executive Summary
Online customer reviews significantly influence purchasing decisions. However, the prevalence of fake, paid, or deceptive reviews damages consumer trust and distorts product rankings. This research explores Natural Language Processing (NLP) techniques and Supervised Machine Learning algorithms to build an automated, highly accurate Fake Review Detection System.

---

## 2. Characteristics of Fake vs. Real Reviews

| Feature Dimension | Genuine (Real) Reviews | Deceptive (Fake) Reviews |
| :--- | :--- | :--- |
| **Language Pattern** | Specific product details, balanced feedback, natural tone | Generic praise/hate, extreme superlatives, vague descriptions |
| **Sentiment** | Mixed/nuanced (mentions pros and minor cons) | Polarized (100% positive or 100% negative) |
| **Promotional Markers** | Rare | High occurrence of links (`http`), discount codes, 'BUY NOW' |
| **Punctuation & Caps** | Standard capitalization | Excessive exclamation marks (`!`), ALL-CAPS text |
| **Text Length** | Moderate to long, descriptive | Very short (one-liners) or repeated copypasta |

---

## 3. NLP Feature Engineering Pipeline

### A. Preprocessing Techniques
1. **Lowercasing**: Standardize text case to prevent vocabulary duplication.
2. **HTML & URL Removal**: Strip `<a href="...">` tags and promotional URLs using regular expressions (`http\S+|www\.\S+`).
3. **Punctuation & Digit Filtering**: Filter out non-alphabetic characters.
4. **Stopword Removal**: Remove common English function words (*the, is, at, which*) using NLTK stopword lists.
5. **Lemmatization**: Convert words to base dictionary forms using NLTK `WordNetLemmatizer` (*e.g., "running" &rarr; "run"*).

### B. Feature Representation: TF-IDF
Term Frequency-Inverse Document Frequency (TF-IDF) converts text tokens into numerical vectors:

$$\text{TF-IDF}(t, d, D) = \text{TF}(t, d) \times \log\left(\frac{N}{\text{DF}(t)}\right)$$

- **N-grams**: Unigrams and Bigrams (`ngram_range=(1, 2)`) capture single words and key phrase pairs (*e.g., "fast delivery", "free gift"*).

---

## 4. Machine Learning Model Comparison

1. **Logistic Regression (Baseline Model)**
   - High precision on linear boundaries.
   - Outputs probabilistic confidence scores ($0.0 - 1.0$) via the Sigmoid function.
   - Robust against overfitting on sparse text matrices.

2. **Multinomial Naive Bayes**
   - Fast training and low computational overhead.
   - Computes prior probability distributions over vocabulary features.

---

## 5. Evaluation Metrics
- **Accuracy**: Overall classification correctness.
- **Precision**: Ratio of correctly identified fake reviews over all flagged fakes.
- **Recall**: Ratio of detected fakes out of total actual fake reviews.
- **F1-Score**: Harmonic mean of Precision and Recall.
- **Confusion Matrix**: Visualizing False Positives vs. False Negatives.
