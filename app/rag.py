from langchain_aws.retrievers import AmazonKnowledgeBasesRetriever
from langchain_groq import ChatGroq

from .aws import make_client, settings

SYSTEM_PROMPT = """
    You answer questions only the provided content from the user documents. 
    --- Context can contain images, charts and tables. look at the images and explain what they show.
    -- If the answer is not the context, say 'You could not find it.'
"""

def get_retrieve(user_id:int):
    return AmazonKnowledgeBasesRetriever(
        knowledge_base_id=settings.kb_id,
        client=make_client("bedrock-agent-runtime"),
        retrieval_config={
            "vectorSearchConfiguration": 
                {
                    "numberOfResults": 4,
                    "filter": {"equals": {"key":"user_id", "value":user_id}}
                    }
            },
    )
    
    
def get_llm() -> ChatGroq:
    return ChatGroq(
        model=settings.groq_model,
        api_key=settings.groq_api_key
    )
    
    
async def generate(query:str, user_id:int):
    retrieve = get_retrieve(user_id)
    docs = await retrieve.ainvoke(query)
    
    if not docs:
        return "I could not find that in your documents"
    
    contexts = ""
    for chunk in docs:
        contexts += chunk.page_content + "\n\n"
    
    llm = get_llm()
    response = await llm.ainvoke([
        {"role":"system", "content":SYSTEM_PROMPT},
        {"role":"user", "content":f"""
            Question: {query},
            Context: {contexts}
         """},
    ])
    
    
    return response.content