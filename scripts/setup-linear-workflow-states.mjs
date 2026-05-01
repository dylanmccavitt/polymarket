#!/usr/bin/env node

const apiKey = process.env.LINEAR_API_KEY;
const teamKey = process.env.LINEAR_TEAM_KEY || "AGE";

if (!apiKey) {
  console.error("LINEAR_API_KEY is required.");
  process.exit(1);
}

const desiredStates = [
  {
    name: "Ready",
    type: "unstarted",
    color: "#94A3B8",
    position: 1,
    description: "Scoped and ready for Symphony/Codex to pick up."
  },
  {
    name: "Human Review",
    type: "started",
    color: "#8B5CF6",
    position: 4,
    description: "PR and evidence are ready for human review."
  },
  {
    name: "Needs Fixes",
    type: "started",
    color: "#F97316",
    position: 5,
    description: "Review found required fixes; agent should update the same PR."
  },
  {
    name: "Rework",
    type: "started",
    color: "#F59E0B",
    position: 6,
    description: "Implementation needs a broader revision before another review pass."
  },
  {
    name: "Merging",
    type: "started",
    color: "#06B6D4",
    position: 7,
    description: "Human approved; agent may merge and close out."
  },
  {
    name: "Blocked",
    type: "unstarted",
    color: "#EF4444",
    position: 8,
    description: "Blocked by unclear requirements, credentials, environment, or external dependency."
  }
];

async function graphql(query, variables = {}) {
  const response = await fetch("https://api.linear.app/graphql", {
    method: "POST",
    headers: {
      Authorization: apiKey,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ query, variables })
  });

  const payload = await response.json();

  if (!response.ok || payload.errors) {
    console.error(JSON.stringify(payload, null, 2));
    throw new Error(`Linear GraphQL request failed with status ${response.status}`);
  }

  return payload.data;
}

const lookupQuery = `
  query WorkflowSetupLookup {
    teams(first: 250) {
      nodes {
        id
        key
        name
      }
    }
    workflowStates(first: 250) {
      nodes {
        id
        name
        type
        position
        team {
          id
          key
          name
        }
      }
    }
  }
`;

const createMutation = `
  mutation CreateWorkflowState($input: WorkflowStateCreateInput!) {
    workflowStateCreate(input: $input) {
      success
      workflowState {
        id
        name
        type
        position
      }
    }
  }
`;

const data = await graphql(lookupQuery);
const team = data.teams.nodes.find((candidate) => candidate.key === teamKey);

if (!team) {
  console.error(`Could not find Linear team with key ${teamKey}. Set LINEAR_TEAM_KEY if needed.`);
  process.exit(1);
}

const existingStates = data.workflowStates.nodes.filter((state) => state.team?.id === team.id);
const existingNames = new Set(existingStates.map((state) => state.name.toLowerCase()));

console.log(`Team: ${team.name} (${team.key}, ${team.id})`);
console.log("Existing states:");
for (const state of existingStates.sort((a, b) => a.position - b.position)) {
  console.log(`- ${state.name} [${state.type}] position=${state.position}`);
}

for (const state of desiredStates) {
  if (existingNames.has(state.name.toLowerCase())) {
    console.log(`Skip existing: ${state.name}`);
    continue;
  }

  const result = await graphql(createMutation, {
    input: {
      teamId: team.id,
      name: state.name,
      type: state.type,
      color: state.color,
      position: state.position,
      description: state.description
    }
  });

  if (!result.workflowStateCreate.success) {
    throw new Error(`Linear did not create state ${state.name}`);
  }

  const created = result.workflowStateCreate.workflowState;
  console.log(`Created: ${created.name} [${created.type}] position=${created.position}`);
}

console.log("Done. Keep future issues in Backlog until intentionally moved to Ready or Todo.");
