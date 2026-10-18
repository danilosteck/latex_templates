# Prompt inicial

I want to create a structure to use AI agents to help me with bibliometric research. My aim is to have many distinct academic viewpoints for a particular object. I want this structure to be just a blueprint that I will replicate for each study (and possibly share with other people).
The first thing I need to do is to create a structure for this analysis using AI agents. 
Deliverable: Create a plan with basic structure (keep it simple) for AI agents to collect information for a particular study object. This plan should be agnostic to different LLM providers (Anthropic, DeepSeek, OpenAI, Google, etc.) and must be useful for any subject topic. It must be built focusing on gathering academic research and building a map of different viewpoints for the research topic.
My first idea is to create 3 different agents:
1. one that will retrieve information from the web to enrich anything that needs and add to a AI-friendly source. 
2. One agent that will construct the document for MPAs and tech challenges according to what is requested in the Workplan. This agent must not look for outside information, whenever necessary, request the first agent. This agent must refer anything to a verifiable source within an internal reference. 
3. A critical agent, that will evaluate the work done and suggest improvements based on the initial docs.
I want to be consulted in questions regarding the process.
Requirements:
1. The project must be built focusing on optimizing token consumption. Use local caches for anything that is consulted on internet or documents such as PDF and DOCX files (among others).
2. Major focus on indexed paper sources (SCIELO, Web of Science, ScienceDirect / Scopus, Google Scholar, among other major references). 
3. I want a detailed record keeping of the papers analysed and I want them to be traceable and a method of validation if the source exists.