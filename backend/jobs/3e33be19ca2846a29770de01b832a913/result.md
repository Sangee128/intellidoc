# input

| System | MNLI-(m/mm) | QQP | QNLI | SST-2 | CoLA | STS-B | MRPC | RTE | Average |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
|  | 392k | 363k | 108k | 67k | 8.5k | 5.7k | 3.5k | 2.5k |  |
| Pre-OpenAISOTA | 80.6/80.1 | 66.1 | 82.3 | 93.2 | 35.0 | 81.0 | 86.0 | 61.7 | 74.0 |
| BiLSTM+ELMo+Attn | 76.4/76.1 | 64.8 | 79.8 | 90.4 | 36.0 | 73.3 | 84.9 | 56.8 | 71.0 |
| OpenAI GPT | 82.1/81.4 | 70.3 | 87.4 | 91.3 | 45.4 | 80.0 | 82.3 | 56.0 | 75.1 |
| BERT BASE | 84.6/83.4 | 71.2 | 90.5 | 93.5 | 52.1 | 85.8 | 88.9 | 66.4 | 79.6 |
| BERT LARGE | 86.7/85.9 | 72.1 | 92.7 | 94.9 | 60.5 | 86.5 | 89.3 | 70.1 | 82.1 |

Table 1: GLUE Test results, scored by the evaluation server (https://qluebenchmark.com/1eaderboard)
The number below each task denotes the number of training examples. The "Average" column is slightly different
than the official GLUE score, since we exclude the problematic WNLI set. BERT and OpenAI GPT are single
model, single task. F1 scores are reported for QQP and MRPC, Spearman correlations are reported for STS-B, and
accuracy scores are reported for the other tasks. We exclude entries that use BERT as one of their components.

<!-- left column -->
We use a batch size of 32 and fine-tune for 3
epochs over the data for all GLUE tasks. For each
task, we selected the best fine-tuning learning rate
(among 5e-5, 4e-5, 3e-5, and 2e-5) on the Dev set
Additionally, for BERTLARGE we found that fine-.
tuning was sometimes unstable on small datasets
so we ran several random restarts and selected the
best model on the Dev set. With random restarts
we use the same pre-trained checkpoint but per
form different fine-tuning data shuffling and clas

BERTBASE and BERTLARGE outperform all sys
tems on all tasks by a substantial margin, obtaining
4.5% and 7.0% respective average accuracy im
provement over the prior state of the art. Note tha
BERTbAsE and OpenAI GPT are nearly identical
in terms of model architecture apart from the at
tention masking. For the largest and most widely
reported GLUE task, MNLI, BERT obtains a 4.6%
absolute accuracy improvement. On the official

of 80.5, compared to OpenAI GPT, which obtains
72.8 as of the date of writing.
We find that BERTLARGE significantly outper
forms BERTBAsE across all tasks, especially those
with very little training data. The effect of mode.
size is explored more thoroughly in Section 5.2.

## 4.2 SOuAD v1.1

The Stanford Question Answering Dataset
(SQuAD v1.1) is a collection of 100k crowd
sourced question/answer pairs (Rajpurkar et al..
2016). Given a question and a passage from.

> 9The GLUE data set distribution does not include the Tes
> labels, and we only made a single GLUE evaluation serve
> submission for each of BERTBAsE and BERTLARGE.


<!-- right column -->
Wikipedia containing the answer, the task is tc
predict the answer text span in the passage.
As shown in Figure 1, in the question answer
ing task, we represent the input question and pas
sage as a single packed sequence, with the ques
tion using the A embedding and the passage using
the B embedding. We only introduce a start vec
tor S E RH and an end vector E E RH during
fine-tuning. The probability of word i being the
start of the answer span is computed as a dot prod
uct between T, and S followed by a softmax over
eS.T

all of the words in the paragraph: P, =

; eS Tj
The analogous formula is used for the end of the
answer span. The score of a candidate span fron
position i to position j is defined as S-T, + E-T;
and the maximum scoring span where j  i is
used as a prediction. The training objective is the
sum of the log-likelihoods of the correct start and
end positions. We fine-tune for 3 epochs with a
learning rate of 5e-5 and a batch size of 32.
Table 2 shows top leaderboard entries as well
as results from top published systems (Seo et al.
2017; Clark and Gardner, 2018; Peters et al.
2018a; Hu et al., 2018). The top results from the
SQuAD leaderboard do not have up-to-date public
system descriptions available,11 and are allowed to
use any public data when training their systems.
We therefore use modest data augmentation in
our system by first fine-tuning on TriviaQA (Joshi
et al., 2017) befor fine-tuning on SQuAD.
Our best performing system outperforms the top.
leaderboard system by +1.5 F1 in ensembling and
+1.3 F1 as a single system. In fact, our single
BERT model outperforms the top ensemble sys
tem in terms of F1 score Without TriviaOA fin

> QANet is described in Yu et al. (20i8), but the system
> has improved substantially after publication
