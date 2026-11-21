-- The old Customer Service starter text forbade answering anything not in the knowledge files, so the agent
-- refused even general questions. Update agents that still have that exact text (edited ones are left alone).
UPDATE agents SET instructions = 'You are the customer service agent for {business}. Be warm and brief: two or three sentences. Help customers with orders, returns and questions about {business}.'
WHERE instructions = 'You are the customer service agent for {business}. Be warm and brief — two or three sentences. Only answer from the knowledge sources. If you are not sure, say a teammate will follow up.';
