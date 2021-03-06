import re
import torch
#from nltk.tokenize import word_tokenize
#from gulordava_code import dictionary_corpus
from helper import get_alt_nums, get_alts, strip_end_punct
import utils
#### french model specific ####

def load_model():
    '''sets up a model for frwac
    Arguments: none
    Returns the model and device'''
    with open("model_frwac.pt", 'rb') as f:
        print("Loading the model")
        # to convert model trained on cuda to cpu model
        model = torch.load(f, map_location=lambda storage, loc: storage)
    model.eval() #put model in eval mode
    model.cpu() # put it on cpu
    device = torch.device("cpu") #what sort of data model is stored on
    return (model, device)

def load_dict():
    '''loads the dictionary
    Arguments: none
    Returns dictionary and length of dictionary'''
    dictionary = utils.Dictionary()
    dictionary.load("frwac_dicts.json") #load a dictionary
    ntokens = len(dictionary)
    return(dictionary, ntokens)
    
def tokenize(word):
    '''takes a word, returns it split into tokens to match tokenization that french model I think? expects'''
    new_string = re.sub("([.,?!])", r" \1 ", word) # split some punctuation as their own words
    newer_string = re.sub("'", "' ", new_string) # split words after apostrophes
    tokens = newer_string.split()
    return tokens

def new_sentence(model, device, ntokens):
    '''sets up a new sentence for gulordava model
    Arguments: model, device as from load_model, ntokens = length of dictionary
    returns a word placeholder and an initialized hidden layer'''
    hidden = model.init_hidden(1) #sets initial values on hidden layer
    input_word = torch.randint(ntokens, (1, 1), dtype=torch.long).to(device) #make a word placeholder
    return (input_word, hidden)

def update_sentence(word, input_word, model, hidden, dictionary):
    '''takes in a sentence so far adds the next word and returns the new list of surprisals
    Arguments:
    word = next word in sentence
    input_word = placeholder for wordid
    model = model from load_model
    hidden = hidden layer representation of sentence so far
    dictionary = dictionary from load_dict
    Returns: output = (probably not needed??)
    hidden = new hidden layer
    word_surprisals = distribution of surprisals for all words'''
    parts = tokenize(word) #get list of tokens
    for part in parts:
        if part not in dictionary.word2idx:
            print("Good word "+part+" is unknown") #error message
        word_idx = dictionary.word2idx[part]        
        input_word.fill_(word_idx) #fill with value of token
        output, hidden = model(input_word, hidden) #do the model thing
        word_weights = output.squeeze().div(1.0).exp().cpu() #process output into weights
        word_surprisals = -1*torch.log2(word_weights/sum(word_weights))# turn into surprisals
    return (hidden, word_surprisals)

def get_surprisal(surprisals, dictionary, word):
    '''Find the surprisal for a word given a context
    Arguments:
    surprisals - surprisal distribution
    dictionary - word to word id dictionary
    word - word we want surprisal for 
    Returns the numeric surprisal value of the word, if word is unknown returns -1
    We don't trust surprisal values for UNK words'''
    if word not in dictionary.word2idx:
        print(word+" is unknown")
        return -1 #use -1 as an error code
    else:
        word_idx = dictionary.word2idx[word]   
    return surprisals[word_idx].item() #numeric value of word's surprisal

def find_bad_enough(num_to_test, minimum, word_list, surprisals_list, dictionary):
    '''Finds an adequate distractor word
    either the first word that meets minimum surprisal for all sentences or the best if
    it tries num_to_test and none meet the minimum
    Arguments:
    num_to_test = an integer for how many candidate words to try
    minimum = minimum surprisal desired
    (will return first word with at least this surprisal for all sentences)
    word_list = the good words that occur in this position
    surprisals_list = distribution of surprisals (from update_sentence)
    dictionary = word to word_id lok up
    returns: chosen distractor word'''
    best_word = ""
    best_surprisal = 0
    length, freq = get_alt_nums(word_list) #get average length, frequency
    i = 1
    k = 0
    options_list = get_alts(length, freq)
    while options_list is None:
        new_opts_1 = get_alts(length, freq+i) # find words with that length and frequency
        new_opts_2 = get_alts(length, freq-i)
        i += 1 #if there weren't any, try a slightly higher frequency
        options_list=new_opts_1
        if options_list is None:
            options_list=new_opts_2
        else:
            options_list.extend(new_opts_2)
    while best_surprisal == 0 or k < num_to_test: #no word has a real surprisal value or we haven't tested enough
        min_surprisal = 100 #dummy value higher than we expect any surprisal to actually be
        while k == len(options_list): # if we run out of options
            new_opts_1 = get_alts(length, freq+i) #keep trying to find higher frequency words
            new_opts_2 = get_alts(length, freq-i)
            i += 1
            if new_opts_1 is not None:
                options_list.extend(new_opts_1) #add to the options list
            if new_opts_2 is not None:
                options_list.extend(new_opts_2)
        word = options_list[k] #try the kth option
        k += 1
        for j, _ in enumerate(surprisals_list): # for each sentence
            surprisal = get_surprisal(surprisals_list[j], dictionary, word) #find that word
            min_surprisal = min(min_surprisal, surprisal) #lowest surprisal so far
        if min_surprisal >= minimum: #if surprisal in each condition is adequate
            return word # we found a word to use and are done here
        if min_surprisal > best_surprisal: #if it's the best option so far, record that
            best_word = word
            best_surprisal = min_surprisal
    print("Couldn't meet surprisal target, returning with surprisal of "+str(best_surprisal)) #return best we have
    return best_word
    
def do_sentence_set(sentence_set, model, device, dictionary, ntokens):
    '''Processes a set of sentences that get the same distractors
    Arguments:
    sentence_set = a list of sentences (all equal length)
    model, device = from load_model
    dictionary, ntokens = from load_dictionary
    returns a sentence format string of the distractors'''
    bad_words=[]
    words = []
    sentence_length = len(sentence_set[0].split()) #find length of first item
    for i, _ in enumerate(sentence_set):
        bad_words.append(["x-x-x"])
        sent_words = sentence_set[i].split()
        if len(sent_words) != sentence_length:
            print("inconsistent lengths!!")  #complain if they aren't the same length
        words.append(sent_words) # make a new list with the sentences as word lists
    hidden = [None]*len(sentence_set) #set up a bunch of stuff
    input_word = [None]*len(sentence_set)
    surprisals = [None]*len(sentence_set)
    for i in range(len(sentence_set)): # more set up
        input_word[i], hidden[i] = new_sentence(model, device, ntokens)
    for j in range(sentence_length-1): # for each word position in the sentence
        word_list = []
        for i in range(len(sentence_set)): # for each sentence
            hidden[i], surprisals[i] = update_sentence(words[i][j], input_word[i], model, hidden[i], dictionary) # and the next word to the sentence
            word_list.append(words[i][j+1]) #add the word after that to a list of words
        bad_word = find_bad_enough(100, 21, word_list, surprisals, dictionary) #find an alternate word
        #using the surprisals and matching frequency for the good words; try 100 words, aim for surprisal of 21 or higher
        for l, _ in enumerate(sentence_set):
            cap=word_list[l][0].isupper() # what is capitization of good word in ith sentence
            if cap: #capitalize it
                mod_bad_word=bad_word[0].upper()+bad_word[1:]
            else: #keep lower case
                mod_bad_word=bad_word
            mod_bad_word = mod_bad_word+strip_end_punct(word_list[l])[1] #match end punctuation
            bad_words[l].append(mod_bad_word) # add the fixed bad word to a running list for that sentence
    bad_sentences=[]
    for i, _ in enumerate(bad_words):
        bad_sentences.append(" ".join(bad_words[i]))
    return bad_sentences # and return
