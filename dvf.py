#!/usr/bin/env python
# title             :dvf.py
# description       :Identifying viral sequences from metagenomic data by deep learning
# author            :Jie Ren renj@usc.edu
# date              :20180807
# version           :1.0
# usage             :python dvf.py -i <path_to_input_fasta> -o <path_to_output_directory>
# required packages :numpy, theano, keras 
# conda create -n dvf python=3.6 numpy theano keras scikit-learn Biopython
#==============================================================================


#### Step 0: pass arguments into the program ####
import os, sys, optparse, warnings
from turtle import forward
from Bio import SeqIO

prog_base = os.path.split(sys.argv[0])[1]
parser = optparse.OptionParser()
parser.add_option("-i", "--in", action = "store", type = "string", dest = "input_fa", 
                  help = "input fasta file")
parser.add_option("-m", "--mod", action = "store", type = "string", dest = "modDir",
                                    default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "models"), 
                  help = "model directory (default ./models)")
parser.add_option("-o", "--out", action = "store", type = "string", dest = "output_dir",
                                    default='./', help = "output directory")
parser.add_option("-l", "--len", action = "store", type = "int", dest = "cutoff_len",
                                    default=1, help = "predict only for sequence >= L bp (default 1)")
parser.add_option("-c", "--core", action = "store", type = "int", dest = "core_num",
                                    default=1, help = "number of parallel cores (default 1)")

(options, args) = parser.parse_args()
if (options.input_fa is None) :
    sys.stderr.write(prog_base + ": ERROR: missing required command-line argument")
    filelog.write(prog_base + ": ERROR: missing required command-line argument")
    parser.print_help()
    sys.exit(0)

input_fa = options.input_fa
if options.output_dir != './' :
    output_dir = options.output_dir
else :
    output_dir = os.path.dirname(os.path.abspath(input_fa))
if not os.path.exists(output_dir):
    os.makedirs(output_dir)
cutoff_len = options.cutoff_len
core_num = options.core_num


#### Step 0: import keras libraries ####
import h5py, multiprocessing
import numpy as np

# os.environ['KERAS_BACKEND'] = 'theano'
import keras
from keras.models import load_model
import tensorflow as tf


#### Step 0: function for encoding sequences into matrices of size 4 by n ####
def encodeSeq(seq) : 
    seq_code = list()
    for pos in range(len(seq)) :
        letter = seq[pos]
        if letter in ['A', 'a'] :
            code = [1,0,0,0]
        elif letter in ['C', 'c'] :
            code = [0,1,0,0]
        elif letter in ['G', 'g'] :
            code = [0,0,1,0]
        elif letter in ['T', 't'] :
            code = [0,0,0,1]
        else :
            code = [1/4, 1/4, 1/4, 1/4]
        seq_code.append(code)
    return seq_code 
def nt2index(nucleotide: str):
        nucleotide = nucleotide.upper()
        if nucleotide == "A":
            return 0
        elif nucleotide == "C":
            return 1
        elif nucleotide == "G":
            return 2
        elif nucleotide == "T":
            return 3
        else:
            return 4
if __name__ == "__main__":
    if core_num > 1:
        pool = multiprocessing.Pool(core_num)
    tf.config.threading.set_inter_op_parallelism_threads(core_num)
    gpus = tf.config.experimental.list_physical_devices('GPU')
    for gpu in gpus:
        tf.config.experimental.set_memory_growth(gpu, True)
        tf.compat.v1.disable_eager_execution()


    def seq2intseq(seq, contig_length=None):
        """Convert genome sequence into indexed sequence

        :param seq: genome sequence
        :type seq: str
        :param contig_length: If designated, sample a subsequence with length contig_length from the original sequence, defaults to None
        :type contig_length: int, optional
        :return: A numpy array
        :rtype: np.ndarray
        """
        if contig_length:
            if len(seq) <= contig_length:
                seq_int = np.zeros(contig_length)
                seq_int[: len(seq)] = list(map(nt2index, str(seq)))
            else:
                start_idx = np.random.randint(len(seq) - contig_length)
                seq_int = np.array(list(map(nt2index, str(seq[start_idx : start_idx + contig_length]))))
            return seq_int
        else:
            if core_num == 1:
                return np.array(list(map(nt2index, str(seq))))
            else:
                output = pool.map(nt2index, str(seq))
                return np.array(output)


    def int2onehot(array):
        n = 5
        output = np.eye(int(n))[array.astype(int)]
        output[output[:, 4] == 1, :] = 0.25
        return output


    def seq2onehot(seq, contig_length=None):
        assert isinstance(seq, str), "Input should be str"
        int_seq = seq2intseq(seq, contig_length)
        onehot = int2onehot(int_seq)
        return onehot[:, :4]
    
    
    complement = {'A': 'T', 'C': 'G', 'G': 'C', 'T': 'A', 'N': 'N'}
#seq = "TCGGGCCC"
#reverse_complement = "".join(complement.get(base, base) for base in reversed(seq))
  
    
#### Step 0: function for predicting viral score using the trained model ####
    def pred(ID) :
        codefw = code[ID]
        # codebw = codeR[ID]
        head = seqname[ID]
        
        #print('predicting '+head)
        # seqL = len(codefw)
        seqL = codefw.shape[0]
        
        if seqL < 300 :
            model = modDict['0.15']
            null = nullDict['0.15']
        elif seqL < 500 and seqL >= 300 :
            model = modDict['0.3']
            null = nullDict['0.3']
        elif seqL < 1000 and seqL >= 500 :
            model = modDict['0.5']
            null = nullDict['0.5']
        else :
            model = modDict['1']
            null = nullDict['1']
        
        # forward = np.array([codefw])
        forward = codefw[None, :, :]
        backward = forward[:, ::-1,::-1]

        # score = model.predict([np.array([codefw]), np.array([codebw])], batch_size=1)
        score = model.predict([forward, backward], batch_size=1, verbose=0)
        pvalue = sum([x>score for x in null])/len(null)
        
        writef = predF.write('\t'.join([head, str(seqL), str(float(score)), str(float(pvalue))])+'\n')
        flushf = predF.flush()
        
        return [head, float(score), float(pvalue)]


#### Step 1: load model ####
    print("1. Loading Models.")
    #modDir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
    modDir = options.modDir
    print("   model directory {}".format(modDir))

    modDict = {}
    nullDict = {}

    warnings.filterwarnings('ignore', 'Error in loading the saved optimizer ')
    warnings.filterwarnings('ignore', 'optimizer ')

    for contigLengthk in ['0.15', '0.3', '0.5', '1'] :
        modPattern = 'model_siamese_varlen_'+contigLengthk+'k'
        modName = [ x for x in os.listdir(modDir) if modPattern in x and x.endswith(".h5") ][0]
        #model_1000 = load_model(os.path.join(modDir, modName))
        modDict[contigLengthk] = load_model(os.path.join(modDir, modName))
        Y_pred_file = [ x for x in os.listdir(modDir) if modPattern in x and "Y_pred" in x ][0]
        with open(os.path.join(modDir, Y_pred_file)) as f:
            tmp = [line.split() for line in f][0]
            Y_pred = [float(x) for x in tmp ]
        Y_true_file = [ x for x in os.listdir(modDir) if modPattern in x and "Y_true" in x ][0]
        with open(os.path.join(modDir, Y_true_file)) as f:
            tmp = [ line.split()[0] for line in f]
            Y_true = [ float(x) for x in tmp ]   
        nullDict[contigLengthk] =  Y_pred[:Y_true.index(1)]  


    #### Step2 : encode sequences in input fasta, and predict scores ####

    # clean the output file
    outfile = os.path.join(output_dir, os.path.basename(input_fa)+'_gt'+str(cutoff_len)+'bp_dvfpred.txt')
    predF = open(outfile, 'w')
    writef = predF.write('\t'.join(['name', 'len', 'score', 'pvalue'])+'\n')
    predF.close()
    predF = open(outfile, 'a')
    #flushf = predF.flush()

    print("2. Encoding and Predicting Sequences.")
    # with open(input_fa, 'r') as faLines :
    #     code = []
    #     codeR = []
    #     seqname = []
    #     head = ''
    #     lineNum = 0
    #     seq = ''
    #     flag = 0
    #     for line in faLines :
    #         #print(line)
    #         lineNum += 1
    #         if flag == 0 and line[0] == '>' :
    #             print("   processing line "+str(lineNum))
    #             head = line.strip()[1:]
    #             continue
    #         elif line[0] != '>' :
    #             seq = seq + line.strip()
    #             flag += 1
    #         elif flag > 0 and line[0] == '>' :
    #             countN = seq.count("N")
    #             if countN/len(seq) <= 0.3 and len(seq) >= cutoff_len : 
    #                 codefw = encodeSeq(seq)
    #                 # seqR = "".join(complement.get(base, base) for base in reversed(seq))
    #                 # codebw = encodeSeq(seqR)
    #                 code.append(codefw)
    #                 # codeR.append(codebw)
    #                 seqname.append(head)
    #                 if len(seqname) % 100 == 0 :
    #                     print("   processing line "+str(lineNum))
    #                     # pool = multiprocessing.Pool(core_num)
    #                     # head, score, pvalue = zip(*pool.map(pred, range(0, len(code))))
    #                     # pool.close()
    #                     head, score, pvalue = zip(*map(pred, range(0, len(code))))
                        
    #                     code = []
    #                     # codeR = []
    #                     seqname = []
    #             else :
    #                 if countN/len(seq) > 0.3 :
    #                     print("   {} has >30% Ns, skipping it".format(head))
    #                 # else :
    #                 #    print("   {} < {}bp, skipping it".format(head, cutoff_len))
                
    #             flag = 0
    #             seq = ''
    #             head = line.strip()[1:]

    #     if flag > 0 :
    #         countN = seq.count("N")
    #         if countN/len(seq) <= 0.3 and len(seq) >= cutoff_len : 
    #             codefw = encodeSeq(seq)
    #             # seqR = "".join(complement.get(base, base) for base in reversed(seq))
    #             # codebw = encodeSeq(seqR)
    #             code.append(codefw)
    #             # codeR.append(codebw)
    #             seqname.append(head)

    #         print("   processing line "+str(lineNum))
    #         # pool = multiprocessing.Pool(core_num)
    #         # head, score, pvalue = zip(*pool.map(pred, range(0, len(code))))
    #         # pool.close()
    #         head, score, pvalue = zip(*map(pred, range(0, len(code))))

    code = []
    seqname = []
    from tqdm import tqdm
    for i, record in enumerate(tqdm(SeqIO.parse(input_fa, "fasta"))) :
        code.append(seq2onehot(str(record.seq)))
        seqname.append(record.id)
        pred(i)
        # if i % 100 == 0 :
        #     # print("   processing line "+str(i))
        #     head, score, pvalue = zip(*map(pred, range(0, len(code))))
        #     code = []
        #     seqname = []
    # if len(code) > 0 :
        # head, score, pvalue = zip(*map(pred, range(0, len(code))))

    predF.close()
    if core_num >1 :
        pool.close()

    print("3. Done. Thank you for using DeepVirFinder.")
    print("   output in {}".format(outfile))









