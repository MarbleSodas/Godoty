"""
Planning Agent Demo for Godot Integration.

This script demonstrates how a planning agent would use the debug tools
to analyze a Godot project and create an execution plan.
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional

# Import planning-focused tools
from agents.tools import (
    # Connection
    ensure_godot_connection,

    # Debug tools for analysis
    get_project_overview,
    analyze_scene_tree,
    capture_visual_context,
    search_nodes,
    get_project_overview,
    get_debug_output,
    analyze_project_structure,
    inspect_scene_file
)

# Import data classes
from agents.tools import (
    SceneInfo,
    NodeInfo,
    VisualSnapshot
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PlanningSession:
    """A planning session for Godot project analysis."""

    def __init__(self):
        self.project_context: Dict[str, Any] = {}
        self.analysis_results: Dict[str, Any] = {}
        self.plan: List[Dict[str, Any]] = []

    async def initialize(self) -> bool:
        """Initialize the planning session by connecting to Godot."""
        logger.info("Initializing planning session...")
        return await ensure_godot_connection()

    async def gather_project_context(self) -> Dict[str, Any]:
        """Gather comprehensive project context."""
        logger.info("Gathering project context...")

        # Get project overview
        overview = await get_project_overview()
        self.project_context.update(overview)

        # Analyze current scene
        scene_analysis = await analyze_scene_tree(detailed=True)
        self.project_context['scene_analysis'] = scene_analysis

        # Capture visual context
        visual_context = await capture_visual_context()
        self.project_context['visual_context'] = visual_context

        # Get recent debug output
        debug_output = await get_debug_output(lines=50)
        self.project_context['debug_output'] = debug_output

        # Analyze project structure
        structure_analysis = await analyze_project_structure()
        self.project_context['structure_analysis'] = structure_analysis

        logger.info("Project context gathered successfully")
        return self.project_context

    async def identify_patterns_and_issues(self) -> List[str]:
        """Identify patterns and potential issues in the project."""
        logger.info("Identifying patterns and issues...")

        insights = []

        # Analyze scene complexity
        scene_analysis = self.project_context.get('scene_analysis', {})
        if scene_analysis:
            analysis = scene_analysis.get('analysis', {})
            total_nodes = analysis.get('total_nodes', 0)
            depth = analysis.get('depth', 0)
            complexity_score = analysis.get('complexity_score', 0)

            if total_nodes > 100:
                insights.append(f"Scene has {total_nodes} nodes - consider optimization")

            if depth > 8:
                insights.append(f"Scene hierarchy is {depth} levels deep - consider flattening")

            if complexity_score > 50:
                insights.append(f"Scene complexity score is {complexity_score:.1f} - high complexity detected")

        # Analyze node types
        node_types = analysis.get('node_types', {})
        if node_types:
            most_common = max(node_types.items(), key=lambda x: x[1])
            insights.append(f"Most common node type: {most_common[0]} ({most_common[1]} instances)")

        # Check for common issues
        if 'recommendations' in scene_analysis:
            insights.extend(scene_analysis['recommendations'])

        # Analyze project structure
        structure = self.project_context.get('structure_analysis', {})
        if structure:
            recommendations = structure.get('recommendations', [])
            insights.extend(recommendations)

        # Analyze debug output for errors
        debug_output = self.project_context.get('debug_output', [])
        error_count = len([line for line in debug_output if 'ERROR' in line.upper()])
        if error_count > 0:
            insights.append(f"Found {error_count} errors in recent debug output")

        self.analysis_results['insights'] = insights
        logger.info(f"Identified {len(insights)} insights and patterns")
        return insights

    async def search_for_specific_patterns(self) -> Dict[str, List[NodeInfo]]:
        """Search for specific patterns in the project."""
        logger.info("Searching for specific patterns...")

        patterns = {}

        # Search for player-related nodes
        player_nodes = await search_nodes("name", "player")
        if player_nodes:
            patterns['player_nodes'] = player_nodes
            logger.info(f"Found {len(player_nodes)} player-related nodes")

        # Search for enemy nodes
        enemy_nodes = await search_nodes("group", "enemies")
        if enemy_nodes:
            patterns['enemy_nodes'] = enemy_nodes
            logger.info(f"Found {len(enemy_nodes)} enemy nodes")

        # Search for UI nodes
        ui_nodes = await search_nodes("type", "Control")
        if ui_nodes:
            patterns['ui_nodes'] = ui_nodes
            logger.info(f"Found {len(ui_nodes)} UI nodes")

        # Search for script nodes
        script_nodes = await search_nodes("script", "")
        if script_nodes:
            patterns['script_nodes'] = script_nodes
            logger.info(f"Found {len(script_nodes)} nodes with scripts")

        # Search for physics nodes
        physics_types = ["CharacterBody2D", "RigidBody2D", "StaticBody2D", "Area2D"]
        physics_nodes = []
        for phys_type in physics_types:
            nodes = await search_nodes("type", phys_type)
            physics_nodes.extend(nodes)

        if physics_nodes:
            patterns['physics_nodes'] = physics_nodes
            logger.info(f"Found {len(physics_nodes)} physics nodes")

        self.analysis_results['patterns'] = patterns
        return patterns

    def generate_execution_plan(self, objective: str) -> List[Dict[str, Any]]:
        """Generate an execution plan based on analysis."""
        logger.info(f"Generating execution plan for: {objective}")

        plan = []

        # Get analysis results
        insights = self.analysis_results.get('insights', [])
        patterns = self.analysis_results.get('patterns', {})

        # Base planning steps
        plan.append({
            "step": 1,
            "title": "Project Assessment",
            "description": f"Assess current project state and requirements for {objective}",
            "tools_required": ["get_project_overview", "analyze_scene_tree"],
            "estimated_time": "2-5 minutes",
            "dependencies": [],
            "risk_level": "LOW"
        })

        # Add specific steps based on objective
        if "performance" in objective.lower():
            plan.extend(self._generate_performance_plan(insights, patterns))
        elif "ui" in objective.lower():
            plan.extend(self._generate_ui_plan(patterns))
        elif "gameplay" in objective.lower():
            plan.extend(self._generate_gameplay_plan(patterns))
        elif "cleanup" in objective.lower() or "organize" in objective.lower():
            plan.extend(self._generate_cleanup_plan(insights, patterns))
        else:
            plan.extend(self._generate_general_plan(insights, patterns))

        # Add validation step
        plan.append({
            "step": len(plan) + 1,
            "title": "Validation and Testing",
            "description": "Test changes and validate that objectives are met",
            "tools_required": ["play_scene", "capture_visual_context", "get_debug_output"],
            "estimated_time": "5-10 minutes",
            "dependencies": [len(plan) - 1],
            "risk_level": "LOW"
        })

        self.plan = plan
        logger.info(f"Generated execution plan with {len(plan)} steps")
        return plan

    def _generate_performance_plan(self, insights: List[str], patterns: Dict) -> List[Dict]:
        """Generate plan for performance optimization."""
        plan = []

        # Check for scene complexity issues
        if any("complexity" in insight.lower() for insight in insights):
            plan.append({
                "step": 2,
                "title": "Scene Complexity Analysis",
                "description": "Analyze and reduce scene complexity",
                "tools_required": ["analyze_scene_tree", "search_nodes"],
                "estimated_time": "10-15 minutes",
                "dependencies": [1],
                "risk_level": "MEDIUM"
            })

        # Check for optimization opportunities
        physics_nodes = patterns.get('physics_nodes', [])
        if len(physics_nodes) > 20:
            plan.append({
                "step": len(plan) + 1,
                "title": "Physics Optimization",
                "description": f"Optimize {len(physics_nodes)} physics nodes for better performance",
                "tools_required": ["search_nodes", "modify_node_property"],
                "estimated_time": "15-20 minutes",
                "dependencies": [len(plan)],
                "risk_level": "MEDIUM"
            })

        return plan

    def _generate_ui_plan(self, patterns: Dict) -> List[Dict]:
        """Generate plan for UI improvements."""
        plan = []

        ui_nodes = patterns.get('ui_nodes', [])
        if not ui_nodes:
            plan.append({
                "step": 2,
                "title": "UI Structure Creation",
                "description": "Create basic UI structure for the project",
                "tools_required": ["create_scene", "create_node"],
                "estimated_time": "10-15 minutes",
                "dependencies": [1],
                "risk_level": "MEDIUM"
            })
        else:
            plan.append({
                "step": 2,
                "title": "UI Analysis and Improvement",
                "description": f"Analyze and improve {len(ui_nodes)} existing UI nodes",
                "tools_required": ["search_nodes", "analyze_scene_tree"],
                "estimated_time": "10-15 minutes",
                "dependencies": [1],
                "risk_level": "LOW"
            })

        return plan

    def _generate_gameplay_plan(self, patterns: Dict) -> List[Dict]:
        """Generate plan for gameplay improvements."""
        plan = []

        player_nodes = patterns.get('player_nodes', [])
        enemy_nodes = patterns.get('enemy_nodes', [])

        if not player_nodes:
            plan.append({
                "step": 2,
                "title": "Player Character Setup",
                "description": "Create or improve player character setup",
                "tools_required": ["create_node", "modify_node_property"],
                "estimated_time": "15-20 minutes",
                "dependencies": [1],
                "risk_level": "MEDIUM"
            })

        if not enemy_nodes:
            plan.append({
                "step": len(plan) + 1,
                "title": "Enemy System Setup",
                "description": "Create enemy system with basic AI",
                "tools_required": ["create_scene", "create_node", "search_nodes"],
                "estimated_time": "20-30 minutes",
                "dependencies": [len(plan)],
                "risk_level": "MEDIUM"
            })

        return plan

    def _generate_cleanup_plan(self, insights: List[str], patterns: Dict) -> List[Dict]:
        """Generate plan for project cleanup and organization."""
        plan = []

        plan.append({
            "step": 2,
            "title": "Node Organization",
            "description": "Organize nodes into logical groups and hierarchies",
            "tools_required": ["search_nodes", "reparent_node"],
            "estimated_time": "15-25 minutes",
            "dependencies": [1],
            "risk_level": "MEDIUM"
        })

        plan.append({
            "step": len(plan) + 1,
            "title": "Scene Structure Optimization",
            "description": "Optimize scene structure based on best practices",
            "tools_required": ["analyze_scene_tree", "create_scene", "delete_node"],
            "estimated_time": "20-30 minutes",
            "dependencies": [len(plan)],
            "risk_level": "HIGH"
        })

        return plan

    def _generate_general_plan(self, insights: List[str], patterns: Dict) -> List[Dict]:
        """Generate general improvement plan."""
        plan = []

        plan.append({
            "step": 2,
            "title": "Structure Analysis",
            "description": "Analyze current structure and identify improvement opportunities",
            "tools_required": ["analyze_scene_tree", "search_nodes"],
            "estimated_time": "10-15 minutes",
            "dependencies": [1],
            "risk_level": "LOW"
        })

        return plan

    def export_plan(self, filename: str = "godot_execution_plan.json") -> str:
        """Export the execution plan to a JSON file."""
        export_data = {
            "project_context": self.project_context,
            "analysis_results": self.analysis_results,
            "execution_plan": self.plan,
            "generated_at": str(asyncio.get_event_loop().time())
        }

        filepath = f"examples/{filename}"
        with open(filepath, 'w') as f:
            json.dump(export_data, f, indent=2, default=str)

        logger.info(f"Plan exported to {filepath}")
        return filepath

    def print_summary(self):
        """Print a summary of the planning session."""
        logger.info("\n" + "=" * 60)
        logger.info("PLANNING SESSION SUMMARY")
        logger.info("=" * 60)

        # Project info
        project_info = self.project_context.get('project_info', {})
        logger.info(f"Project: {project_info.get('name', 'Unknown')}")
        logger.info(f"Path: {project_info.get('path', 'Unknown')}")

        # Scene analysis
        scene_analysis = self.project_context.get('scene_analysis', {})
        if scene_analysis and 'analysis' in scene_analysis:
            analysis = scene_analysis['analysis']
            logger.info(f"Scene: {analysis.get('total_nodes', 0)} nodes, depth {analysis.get('depth', 0)}")

        # Insights
        insights = self.analysis_results.get('insights', [])
        logger.info(f"\nInsights Identified: {len(insights)}")
        for i, insight in enumerate(insights, 1):
            logger.info(f"  {i}. {insight}")

        # Patterns
        patterns = self.analysis_results.get('patterns', {})
        logger.info(f"\nPatterns Found:")
        for pattern_type, nodes in patterns.items():
            logger.info(f"  - {pattern_type}: {len(nodes)} nodes")

        # Plan summary
        logger.info(f"\nExecution Plan: {len(self.plan)} steps")
        for step in self.plan:
            risk_emoji = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴"}.get(step['risk_level'], "⚪")
            logger.info(f"  {step['step']}. {step['title']} {risk_emoji}")


async def main():
    """Run the planning agent demo."""
    logger.info("Starting Planning Agent Demo for Godot Integration")
    logger.info("=" * 60)

    # Create planning session
    session = PlanningSession()

    try:
        # Initialize session
        if not await session.initialize():
            logger.error("Failed to initialize planning session")
            return False

        # Gather project context
        context = await session.gather_project_context()

        # Identify patterns and issues
        insights = await session.identify_patterns_and_issues()

        # Search for specific patterns
        patterns = await session.search_for_specific_patterns()

        # Generate execution plan
        objective = "Improve project organization and performance"
        plan = session.generate_execution_plan(objective)

        # Print summary
        session.print_summary()

        # Export plan
        plan_file = session.export_plan("demo_execution_plan.json")

        logger.info(f"\nPlanning session completed successfully!")
        logger.info(f"Execution plan saved to: {plan_file}")

        return True

    except Exception as e:
        logger.error(f"Planning session failed: {e}")
        return False


if __name__ == "__main__":
    # Run the planning demo
    success = asyncio.run(main())
    exit(0 if success else 1)