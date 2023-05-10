from typing import Any, Tuple

from langchain.chains.combine_documents.base import BaseCombineDocumentsChain
from langchain.chains.question_answering import load_qa_chain
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.llms import OpenAI
from langchain.text_splitter import CharacterTextSplitter
from langchain.vectorstores import FAISS


def prepare_embedding(raw_text: str) -> Tuple[FAISS, BaseCombineDocumentsChain]:
    """
    Prepare embeddings for text.
    """
    text_splitter = CharacterTextSplitter(
        separator="\n\n", chunk_size=1000, chunk_overlap=200, length_function=len
    )
    texts = text_splitter.split_text(raw_text)

    embeddings = OpenAIEmbeddings(disallowed_special=())

    docsearch = FAISS.from_texts(texts=texts, embedding=embeddings)

    qa_chain = load_qa_chain(OpenAI(), chain_type="stuff")

    return docsearch, qa_chain
