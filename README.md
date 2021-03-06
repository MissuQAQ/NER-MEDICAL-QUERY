# NER-MEDICAL-QUERY
BILSTM+CRF NER by pytorch
main structure from (https://github.com/DengYangyong/medical_entity_recognize)

## 1. environments
python==3.7

torch==1.6.0

jieba==0.42.1

## 2.Mark the Sample Data
around 10000 pieces queries from donghuayiwei-jiankangle online medical query platform
Marked by Doccano (https://github.com/doccano/doccano)

## 3.Model Evaulation
There are severe problem at marking data, and the resulting perfomance on dev_set is quite bad (F1-0.565)

## 4.Layout
model folder store the main structure and CRF layer

sql_file store the original sql file (manipulate by pymysql in NER_data)

Batch.py: batch the train sample with similar length of words

build_vocab.py: bagging the characters of train_sample

predict.py: use the model to predict new inputs

NER_data: prepare and clean data

NER_functions: Used functions

NER_parameters: Used parameters

main: train the model

mark_txt_process: transfer the marked queries produced by doccano to standard training sample


### command line performance
![image](https://raw.githubusercontent.com/MissuQAQ/NER-MEDICAL-QUERY/master/image_file/1599204833(1).png)


### data from doccano 
![image](https://raw.githubusercontent.com/MissuQAQ/NER-MEDICAL-QUERY/master/image_file/1599205074(1).png)

### standard training sample
![image](https://raw.githubusercontent.com/MissuQAQ/NER-MEDICAL-QUERY/master/image_file/1599205128(1).png)



## 5.Prediction
carry out the prediction.py on command line


