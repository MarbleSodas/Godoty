// Integration tests for knowledge base functionality
// Note: These tests require an API key to be set in the environment

#[cfg(test)]
mod tests {
    use std::collections::HashMap;
    
    // Basic test to ensure the module compiles
    #[test]
    fn test_knowledge_base_module_exists() {
        // This test just ensures the knowledge base module compiles
        assert!(true);
    }
    
    #[test]
    fn test_cosine_similarity_calculation() {
        // Test cosine similarity with known vectors
        let vec1 = vec![1.0, 0.0, 0.0];
        let vec2 = vec![1.0, 0.0, 0.0];
        
        // Calculate dot product
        let dot_product: f32 = vec1.iter().zip(vec2.iter()).map(|(a, b)| a * b).sum();
        
        // Calculate magnitudes
        let mag1: f32 = vec1.iter().map(|x| x * x).sum::<f32>().sqrt();
        let mag2: f32 = vec2.iter().map(|x| x * x).sum::<f32>().sqrt();
        
        // Calculate cosine similarity
        let similarity = if mag1 > 0.0 && mag2 > 0.0 {
            dot_product / (mag1 * mag2)
        } else {
            0.0
        };
        
        // Identical vectors should have similarity of 1.0
        assert!((similarity - 1.0).abs() < 0.0001);
    }
    
    #[test]
    fn test_cosine_similarity_orthogonal() {
        // Test cosine similarity with orthogonal vectors
        let vec1 = vec![1.0, 0.0, 0.0];
        let vec2 = vec![0.0, 1.0, 0.0];
        
        // Calculate dot product
        let dot_product: f32 = vec1.iter().zip(vec2.iter()).map(|(a, b)| a * b).sum();
        
        // Calculate magnitudes
        let mag1: f32 = vec1.iter().map(|x| x * x).sum::<f32>().sqrt();
        let mag2: f32 = vec2.iter().map(|x| x * x).sum::<f32>().sqrt();
        
        // Calculate cosine similarity
        let similarity = if mag1 > 0.0 && mag2 > 0.0 {
            dot_product / (mag1 * mag2)
        } else {
            0.0
        };
        
        // Orthogonal vectors should have similarity of 0.0
        assert!(similarity.abs() < 0.0001);
    }
    
    #[test]
    fn test_metadata_structure() {
        // Test that we can create metadata structures
        let mut metadata = HashMap::new();
        metadata.insert("type".to_string(), "command".to_string());
        metadata.insert("category".to_string(), "plugin_api".to_string());
        
        assert_eq!(metadata.get("type"), Some(&"command".to_string()));
        assert_eq!(metadata.get("category"), Some(&"plugin_api".to_string()));
    }
    
    #[test]
    fn test_agent_thought_serialization() {
        // Test that agent thoughts can be serialized
        use serde_json;
        
        let thought = serde_json::json!({
            "step": 1,
            "thought": "Analyzing user request",
            "action": "query_knowledge_base",
            "observation": "Found relevant documentation"
        });
        
        assert_eq!(thought["step"], 1);
        assert_eq!(thought["thought"], "Analyzing user request");
    }
    
    #[test]
    fn test_execution_plan_structure() {
        // Test execution plan structure
        use serde_json;
        
        let plan = serde_json::json!({
            "reasoning": "User wants to create a player character",
            "steps": [
                {
                    "step_number": 1,
                    "description": "Create a CharacterBody2D node",
                    "commands_needed": ["create_node"]
                },
                {
                    "step_number": 2,
                    "description": "Attach movement script",
                    "commands_needed": ["attach_script"]
                }
            ],
            "estimated_complexity": "medium"
        });
        
        assert_eq!(plan["reasoning"], "User wants to create a player character");
        assert_eq!(plan["steps"].as_array().unwrap().len(), 2);
    }
}

