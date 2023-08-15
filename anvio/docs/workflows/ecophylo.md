The ecophylo workflow starts with a user-defined target gene ([HMM](https://anvio.org/vocabulary/#hidden-markov-models-hmms)) and a list of assembled genomes and/or metagenomes and results in an %(interactive)s interface that includes (1) a phylogenetic analysis of all genes found in genomes and metagenomes that match to the user-defined target gene, and (2) the distribution pattern of each of these genes across metagenomes if the user provided metagenomic short reads to survey.

The user-defined target genes can be described by an %(hmm-list)s. Furthermore, the assemblies of genomes and/or metagenomes to search these genes can be passed to the workflow via the artifacts %(external-genomes)s and %(metagenomes)s, respectively. Finally, the user can also provide a set of metagenomic short reads via the artifact %(samples-txt)s to recover the distribution patterns of genes.

In a standard run, ecophylo first identifies matching genes based on their [HMM](https://anvio.org/vocabulary/#hidden-markov-models-hmms)s, then clusters them based on sequence similarity at a threshold defined by the user, and finally selects a representative sequence from each cluster that contains more than two genes. Next, ecophylo calculates a phylogenetic tree to infer evolutionary associations between these sequences to produce a NEWICK-formatted %(dendrogram)s. If the user provided a %(samples-txt)s for metagenomic [read recruitment](https://anvio.org/vocabulary/#read-recruitment), the workflow will also perform a [read recruitment](https://anvio.org/vocabulary/#read-recruitment) step to recover and store coverage statistics of the final set of genes for downstream analyses in the form of a %(profile-db)s. The completion of the workflow will yield all files necessary to explore the results through an anvi'o %(interactive)s interface and investigate associations between ecological and evolutionary relationships between target genes. The workflow can use any [HMM](https://anvio.org/vocabulary/#hidden-markov-models-hmms) that models amino acid sequences. Using [single-copy core genes](https://anvio.org/vocabulary/#single-copy-core-gene-scg) such as Ribosomal Proteins will yield taxonomic profiles of metagenomes *de facto*.

The ecophylo workflow has 2 modes which can be designated in the %(workflow-config)s by changing the input files that are provided: [tree-mode](#tree-mode-insights-into-the-evolutionary-patterns-of-target-genes) and [profile-mode](#profile-mode-insights-into-the-ecological-and-evolutionary-patterns-of-target-genes-and-environments). In [tree-mode](#tree-mode-insights-into-the-evolutionary-patterns-of-target-genes), the sequences will be used to calculate a phylogenetic tree. In [profile-mode](#profile-mode-insights-into-the-ecological-and-evolutionary-patterns-of-target-genes-and-environments), the sequences will be used to calculate a phylogenetic tree and be additionally profiled via [read recruitment](https://anvio.org/vocabulary/#read-recruitment) across user-provided metagenomes.

## Required input

The ecophylo workflow requires the following files:

- %(workflow-config)s: This allows you to customize the workflow step by step. Here is how you can generate the default version:

{{ codestart }}
anvi-run-workflow -w ecophylo \
                  --get-default-config config.json
{{ codestop }}


{:.notice}
Here is a tutorial walking through more details regarding the ecophylo %(workflow-config)s file: coming soon!

- %(hmm-list)s: This file designates which HMM should be used to extract the target gene from your %(contigs-db)s.
- %(metagenomes)s and/or %(external-genomes)s: These files hold the assemblies where you are looking for the target gene. Genomes in %(external-genomes)s can be reference genomes, [SAGs](https://anvio.org/vocabulary/#single-amplified-genome-sag), and/or [MAGs](https://anvio.org/vocabulary/#metagenome-assembled-genome-mag).

## Quality control and processing of hmm-hits

[Hidden Markov Models](https://anvio.org/vocabulary/#hidden-markov-models-hmms) are the crux of the EcoPhylo workflow and will determine the sensitivity and specificity of the protein family hmm-hits you seek to investigate. However, not all %(hmm-hits)s are created equal. Just how BLAST can detect spurious hits with [high-scoring segment pairs](https://www.ncbi.nlm.nih.gov/books/NBK62051/), HMMER can detect non-homologous hits as well. To address this, we have a series of parameters you can adjust to fine tune the input set of %(hmm-hits)s that EcoPhylo will process. 

### HMM alignment coverage filtering

The first step to removing bad %(hmm-hits)s is to filter out hits with low quality alignment coverage. This is done with the rule `filter_hmm_hits_by_model_coverage` which leverages %(anvi-script-filter-hmm-hits-table)s. We recommend 80%% model coverage filter for most cases. However, it is always recommended to explore the distribution of model coverage with any new HMM which will help you determine a proper cutoff (citation). To adjust this parameter, go to the `filter_hmm_hits_by_model_coverage` rule and change the parameter `--model-coverage`. 

{:.notice}
Some full gene length HMM models align to a single hmm-hit independently at different coordinates when there should only be one annotation. To merge these independent alignment into one HMM alignment coverage stat, set `--merge-partial-hits-within-X-nts` to any distance between the hits for which you would like to merge.

### Conservative mode: only complete open-reading frames

Genes predicted from genomes and metagenomes can be partial or complete depending on whether a stop and stop codon is detected. Even if you filter out %(hmm-hits)s with bad alignment coverage as discussed above, HMMs can still detect low quality hits due to partial genes (i.e., genes that are not partial and that start with a start codon and end with a stop codon) with good alignment coverage and homology statistics. Unfortunately, partial genes can lead to spurious phylogenetic branches and/or inflate the number of observed populations or functions in a given set of genomes/metagenomes. 

To remove partial genes from the EcoPhylo analysis, the user set `--filter-out-partial-gene-calls True` so that only complete open-reading frames are processed.

```bash
{
    "filter_hmm_hits_by_model_coverage": {
        "threads": 5,
        "--model-coverage": 0.8,
        "--filter-out-partial-gene-calls": true,
        "additional_params": ""
    },
}
```

### Discovery-mode: ALL open-reading frames

However, maybe you're a risk taker, a maverick explorer of metagenomes. Complete or incomplete you accept all genes and their potential tree bending shortcomings! In this case, set `--filter-out-partial-gene-calls false` in the config file.

{:.notice}
Exploring complete and incomplete ORFs will increase the distribution of sequence lengths and thus impact sequence clustering. We recommend adjusting `cluster_X_percent_sim_mmseqs` to `"--cov-mode": 1` to help insure ORFs of all length properly cluster together. Please refer to the [MMseqs2 user guide description of --cov-mode](https://mmseqs.com/latest/userguide.pdf) for more details.

```bash
{
    "filter_hmm_hits_by_model_coverage": {
        "threads": 5,
        "--model-coverage": 0.8,
        "--filter-out-partial-gene-calls": false,
        "additional_params": ""
    },
      "cluster_X_percent_sim_mmseqs": {
      "threads": 5,
      "--min-seq-id": 0.94,
      "--cov-mode": 1,
      "clustering_threshold_for_OTUs": [
          0.99,
          0.98,
          0.97
      ],
      "AA_mode": false
    },
}
```
## tree-mode: Insights into the evolutionary patterns of target genes 

This is the simplest implementation of ecophylo where only an amino acid based phylogenetic tree is calculated. The workflow will extract the target gene from input assemblies, cluster and pick representatives, then calculate a phylogenetic tree based on the amino acid representative sequences. There are two sub-modes of [tree-mode](#tree-mode-insights-into-the-evolutionary-patterns-of-target-genes) which depend on how you pick representative sequences, [NT-mode](#nt-mode) or [AA-mode](#aa-mode) where extracted genes associated nucleotide version (NT) or the amino acid (AA) can be used to cluster the dataset and pick representatives, respectively.

### NT-mode

**Cluster and select representative genes based on NT sequences.**

This is the default version of [tree-mode](#tree-mode-insights-into-the-evolutionary-patterns-of-target-genes) where the extracted gene sequences are clustered based on their associated NT sequences. This is done to prepare for [profile-mode](#profile-mode-insights-into-the-ecological-and-evolutionary-patterns-of-target-genes-and-environments),  where adequate sequence distance is needed between gene NT sequences to prevent [non-specific-read-recruitment](https://anvio.org/vocabulary/#non-specific-read-recruitment). The translated amino acid versions of the NT sequence clusters are then used to calculate an AA based phylogenetic tree. This mode is specifically useful to see what the gene phylogenetic tree will look like before the [read recruitment](https://anvio.org/vocabulary/#read-recruitment) step in [profile-mode](#profile-mode-insights-into-the-ecological-and-evolutionary-patterns-of-target-genes-and-environments),  (for gene phylogenetic applications of ecophylo please see [AA-mode](#Cluster based on AA sequences - AA-mode)). If everything looks good you can add in your %(samples-txt)s and continue with [profile-mode](#profile-mode-insights-into-the-ecological-and-evolutionary-patterns-of-target-genes-and-environments) to add metagenomic [read recruitment](https://anvio.org/vocabulary/#read-recruitment) results.

Here is what the start of the ecophylo %(workflow-config)s should look like if you want to run [tree-mode](#tree-mode-insights-into-the-evolutionary-patterns-of-target-genes):

```bash
{
    "metagenomes": "metagenomes.txt",
    "external_genomes": "external-genomes.txt",
    "hmm_list": "hmm_list.txt",
    "samples_txt": ""
}
```

### AA-mode

**Cluster and select representative genes based on AA sequences. If you are interested specifically in gene phylogenetics, this is the mode for you!**

This is another sub-version of [tree-mode](#tree-mode-insights-into-the-evolutionary-patterns-of-target-genes) where representative sequences are chosen via AA sequence clustering.

To initialize [AA-mode](#aa-mode), go to the rule `cluster_X_percent_sim_mmseqs` in the ecophylo %(workflow-config)s and turn "AA_mode" to true:

```bash
{
    "metagenomes": "metagenomes.txt",
    "external_genomes": "external-genomes.txt",
    "hmm_list": "hmm_list.txt",
    "samples_txt": ""
    "cluster_X_percent_sim_mmseqs": {
        "AA_mode": true,
    }
}
```

{:.notice}
Be sure to change the `--min-seq-id` of the `cluster_X_percent_sim_mmseqs` rule to the appropriate clustering threshold depending if you are in [NT-mode](#nt-mode) or [AA-mode](#aa-mode).

## profile-mode: Insights into the ecological and evolutionary patterns of target genes and environments

[profile-mode](#profile-mode-insights-into-the-ecological-and-evolutionary-patterns-of-target-genes-and-environments),  is an extension of default [tree-mode](#tree-mode-insights-into-the-evolutionary-patterns-of-target-genes) ([NT-mode](#nt-mode)) where NT sequences representatives are profiled with metagenomic reads from user provided metagenomic samples. This allows for the simultaneous visualization of phylogenetic and ecological relationships of genes across metagenomic datasets.

Additional required files:
- %(samples-txt)s

To initialize [profile-mode](#profile-mode-insights-into-the-ecological-and-evolutionary-patterns-of-target-genes-and-environments), , add the path to your %(samples-txt)s to your ecophylo %(workflow-config)s:

```bash
{
    "metagenomes": "metagenomes.txt",
    "external_genomes": "external-genomes.txt",
    "hmm_list": "hmm_list.txt",
    "samples_txt": "samples.txt"
}
```

## Config file options

Ecophylo will sanity check all input files that contain %(contigs-db)ss before the workflow starts. This can take a while especially if you are working with 1000's of genomes. If you want to skip sanity checks for %(contigs-db)ss in your %(external-genomes)s and/or %(metagenomes)s then adjust your config to the following:

```bash
{
    "run_genomes_sanity_check": false
}
```