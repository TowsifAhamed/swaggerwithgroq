import os
import requests
import yaml
import logging
from groq import Groq
import re
import json

# Configure logging
logging.basicConfig(level=logging.INFO)

def extract_json_from_response(sample_data):
    """
    Extract the JSON part from the provided sample data, removing unnecessary text.
    """
    # Use regular expressions to find JSON blocks
    json_matches = re.findall(r'```json(.*?)```', sample_data, re.DOTALL)
    
    if json_matches:
        json_blocks = []
        for match in json_matches:
            try:
                # Clean up the match (removes extra whitespace/newlines)
                json_string = match.strip()
                json_data = json.loads(json_string)
                json_blocks.append(json_data)
            except json.JSONDecodeError:
                logging.error(f"Failed to parse JSON: {match.strip()}")
                continue
        
        return json_blocks if json_blocks else None
    else:
        logging.error("No valid JSON found.")
        return None


def parse_all_responses(api_responses):
    """
    Parse through all the API responses and extract the important JSON.
    """
    parsed_responses = {}

    for endpoint, data in api_responses.items():
        method = data.get("method", "GET")
        sample_data = data.get("sample_data", "")

        # Extract JSON from the sample data
        parsed_json = extract_json_from_response(sample_data)

        if parsed_json:
            parsed_responses[endpoint] = {
                "method": method,
                "response": parsed_json
            }

    return parsed_responses

class OpenAPIGroqDataGenerator:
    def __init__(self, groq_api_key):
        self.groq_client = Groq(api_key=groq_api_key)
        self.definitions = {}

    def fetch_openapi_schema(self, swagger_url):
        """
        Fetch the OpenAPI/Swagger schema from the provided URL.
        Supports both JSON and YAML formats.
        """
        try:
            logging.info(f"Fetching OpenAPI schema from: {swagger_url}")
            response = requests.get(swagger_url)
            logging.debug(f"Response Status Code: {response.status_code}")
            logging.debug(f"Response Content: {response.text}")

            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError:
                    logging.info("Failed to parse as JSON, trying YAML...")
                    return yaml.safe_load(response.text)
            else:
                raise Exception(f"Error fetching OpenAPI schema: {response.status_code}")
        except Exception as e:
            logging.error(f"Failed to fetch schema: {str(e)}")
            return {"error": f"Failed to fetch schema: {str(e)}"}

    def extract_definitions(self, swagger_schema):
        """
        Extract the definitions from the OpenAPI/Swagger schema for easy reference.
        """
        self.definitions = swagger_schema.get('definitions', {})
        logging.info(f"Extracted {len(self.definitions)} definitions.")

    def resolve_ref(self, ref):
        """
        Resolve a $ref to its full definition from the swagger schema.
        """
        ref_path = ref.split('/')
        if len(ref_path) > 1 and ref_path[-2] == 'definitions':
            definition_name = ref_path[-1]
            return self.definitions.get(definition_name, {})
        return {}

    def resolve_schema_properties(self, schema):
        """
        Resolve properties from a schema, including handling references or direct schema objects.
        """
        if "$ref" in schema:
            # Resolve the reference
            resolved_schema = self.resolve_ref(schema["$ref"])
            return resolved_schema.get("properties", {}), resolved_schema.get("required", [])
        else:
            return schema.get("properties", {}), schema.get("required", [])

    def clean_parameters(self, parameters):
        """
        Clean up and structure the parameters for the Groq prompt.
        """
        clean_params = []

        for param in parameters:
            if "schema" in param:
                # Extract the schema details
                schema = param["schema"]
                properties, required = self.resolve_schema_properties(schema)
                
                # Clean up each property
                for prop_name, prop_details in properties.items():
                    clean_params.append({
                        "name": prop_name,
                        "type": prop_details.get("type", "string"),
                        "required": prop_name in required
                    })
            elif "name" in param:
                # Handle simple cases where only the parameter name is given
                clean_params.append({
                    "name": param["name"],
                    "type": param.get("type", "string")
                })
        
        return clean_params if clean_params else None

    def extract_response_data(self, responses):
        """
        Extract response data, including references to definitions, from responses.
        """
        response_data = {}
        
        for status_code, response_details in responses.items():
            schema = response_details.get('schema', {})
            if "$ref" in schema:
                # Resolve the reference
                resolved_schema = self.resolve_ref(schema["$ref"])
                properties = resolved_schema.get("properties", {})
                response_data[status_code] = {prop_name: prop_details.get("type", "string") for prop_name, prop_details in properties.items()}
            else:
                response_data[status_code] = "No schema found"
        
        return response_data

    def create_sample_data_prompt(self, endpoint, parameters, responses):
        """
        Create a prompt for the Groq LLaMA3 model based on the API endpoint, parameters, and responses.
        """
        clean_params = self.clean_parameters(parameters)
        params_text = clean_params if clean_params else "No parameters"

        # Clean responses
        clean_responses = self.extract_response_data(responses)

        prompt = f"""
        Generate realistic sample data for the following API endpoint:
        
        Endpoint: {endpoint}
        Parameters: {params_text}
        Responses: {clean_responses}
        Return only the most realistic JSON response that could be returned by this API.
        """
        logging.debug(f"Created prompt: {prompt}")
        return prompt

    def generate_realistic_data_using_groq(self, prompt):
        """
        Generate realistic data using the Groq LLaMA3 model.
        """
        try:
            logging.info(f"Generating data for prompt: {prompt}")
            response = self.groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama3-8b-8192"
            )
            return response.choices[0].message.content.strip()  # Strip unnecessary text
        except Exception as e:
            logging.error(f"Failed to generate data: {str(e)}")
            return {"error": f"Failed to generate data: {str(e)}"}

    def generate_example_apis(self, swagger_schema):
        """
        Generate example API responses using Groq LLaMA3 for each endpoint in the OpenAPI schema.
        """
        example_apis = {}

        for path, methods in swagger_schema['paths'].items():
            for method, details in methods.items():
                if isinstance(details, dict):
                    parameters = details.get('parameters', [])
                    responses = details.get('responses', {})
                    prompt = self.create_sample_data_prompt(path, parameters, responses)
                    sample_data = self.generate_realistic_data_using_groq(prompt)

                    # Store the generated sample data
                    example_apis[path] = {
                        "method": method.upper(),
                        "sample_data": sample_data
                    }
                    logging.debug(f"Generated sample data for {path}: {sample_data}")
                else:
                    logging.warning(f"Expected details to be a dictionary, but got {type(details)} for path {path} and method {method}")
        
        return example_apis

    def get_generated_data(self, swagger_url):
        """
        Fetch the Swagger schema and generate realistic API data using Groq.
        """
        swagger_schema = self.fetch_openapi_schema(swagger_url)
        if 'error' in swagger_schema:
            return swagger_schema

        # Extract definitions before generating data
        self.extract_definitions(swagger_schema)

        return parse_all_responses(self.generate_example_apis(swagger_schema))
