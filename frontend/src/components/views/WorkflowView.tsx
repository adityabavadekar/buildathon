'use client'
/* eslint-disable @typescript-eslint/no-confusing-void-expression, @typescript-eslint/no-base-to-string, @typescript-eslint/restrict-template-expressions, react-hooks/set-state-in-effect */

import React, { useCallback, useEffect, useState } from 'react'
import {
  Activity,
  BrainCircuit,
  CircleDot,
  Clock3,
  GitBranch,
  Plus,
  RefreshCw,
  Send,
  Timer,
  Trash2,
  UserRound,
  Zap,
} from 'lucide-react'
import {
  getWorkflow,
  getWorkflowAnalytics,
  listWorkflowTemplates,
  createWorkflowTemplate,
  updateWorkflowTemplate,
  deleteWorkflowTemplate,
  listWorkflows,
  getWorkflowOptions,
  launchWorkflow,
  type WorkflowAction,
  type WorkflowTriggerType,
  type WorkflowOptionsResponse,
  sendWorkflowSignal,
  type WorkflowAnalyticsResponse,
  type WorkflowInstance,
  type WorkflowSignalType,
  type WorkflowTemplate,
  type WorkflowTemplateDefinition,
  type WorkflowStoppingRules,
} from '@/lib/api'
import { Badge, type BadgeVariant } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { StatCard } from '@/components/ui/StatCard'
import { SkeletonCard, SkeletonRow } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  addEdge,
  Background,
  Controls,
  ReactFlow,
  ReactFlowProvider,
  applyNodeChanges,
  type Connection,
  type Edge,
  type Node,
  type NodeChange,
  Handle,
  Position,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

interface GraphEditorProps {
  nodes: Array<Record<string, string>>
  edges: Array<Record<string, string>>
  onChange: (
    nodes: Array<Record<string, string>>,
    edges: Array<Record<string, string>>,
  ) => void
  onSelectNode: (node: Record<string, string> | null) => void
}

function GraphEditor({ nodes, edges, onChange, onSelectNode }: GraphEditorProps) {
  const nodeTypes = React.useMemo(
    () => ({
      workflow: ({ data }: { data: { label?: string; type?: string } }) => (
        <div className="relative min-w-32 rounded-control border border-accent/50 bg-surface px-3 py-2 font-mono text-[11px] text-ink">
          <Handle type="target" position={Position.Left} />
          <span className="flex items-center gap-1 text-[10px] text-accent uppercase">
            {iconForNodeType(data.type ?? 'action')}
            {data.type}
          </span>
          <div>{data.label}</div>
          <Handle type="source" position={Position.Right} />
        </div>
      ),
    }),
    [],
  )
  const mappedNodes: Node[] = nodes.map((node, index) => ({
    id: node.id ?? `node-${index + 1}`,
    position: { x: Number(node.x ?? index * 190), y: Number(node.y ?? 80) },
    data: { label: node.label ?? 'Workflow step', type: node.type ?? 'action' },
    type: 'workflow',
  }))
  const mappedEdges: Edge[] = edges.map((edge, index) => ({
    id: edge.id ?? `edge-${index + 1}`,
    source: edge.source ?? '',
    target: edge.target ?? '',
    animated: true,
  }))
  const [flowNodes, setFlowNodes] = React.useState<Node[]>(mappedNodes)
  const [flowEdges, setFlowEdges] = React.useState<Edge[]>(mappedEdges)
  React.useEffect(() => { setFlowNodes(mappedNodes) }, [nodes])
  React.useEffect(() => { setFlowEdges(mappedEdges) }, [edges])
  const handleNodesChange = (changes: NodeChange[]) => {
    const changed = applyNodeChanges(changes, flowNodes)
    setFlowNodes(changed)
    onChange(
      changed.map((node) => ({
        id: node.id,
        label: String(node.data.label ?? 'Workflow step'),
        type: String(node.data.type ?? 'action'),
        x: String(Math.round(node.position.x)),
        y: String(Math.round(node.position.y)),
      })),
      edges,
    )
  }
  const handleConnect = (connection: Connection) => {
    const nextEdges = addEdge(connection, flowEdges)
    setFlowEdges(nextEdges)
    onChange(
      nodes,
      nextEdges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
      })),
    )
  }
  return (
    <ReactFlowProvider>
      <div className="relative h-72 w-full rounded-control border border-border bg-surface" style={{ minHeight: 288 }}>
        <ReactFlow
          nodeTypes={nodeTypes}
          nodes={flowNodes}
          edges={flowEdges}
          onNodesChange={handleNodesChange}
          onConnect={handleConnect}
          onNodeClick={(_, node) => onSelectNode(nodes.find((item) => item.id === node.id) ?? null)}
          fitView
          deleteKeyCode="Delete"
          nodesDraggable
          nodesConnectable
          elementsSelectable
        >
          <Background />
          <Controls />
        </ReactFlow>
      </div>
    </ReactFlowProvider>
  )
}

function labelFor(value: string): string {
  return value.replaceAll('_', ' ')
}

function iconForNodeType(type: string): React.ReactNode {
  if (type === 'trigger') return <CircleDot className="h-3 w-3" />
  if (type === 'decision') return <BrainCircuit className="h-3 w-3" />
  if (type === 'wait') return <Timer className="h-3 w-3" />
  if (type === 'human_handoff') return <UserRound className="h-3 w-3" />
  return <Zap className="h-3 w-3" />
}

function badgeForStage(stage: string): BadgeVariant {
  if (stage === 'COMPLETED') return 'recovered'
  if (stage === 'HUMAN_ESCALATED') return 'escalated'
  if (stage === 'FAILED' || stage === 'CANCELLED') return 'failed'
  return 'pending'
}

function formatTimestamp(timestamp: string): string {
  return new Date(timestamp).toLocaleString()
}

function formatDetails(details: Record<string, unknown>): string {
  return JSON.stringify(details, null, 2)
}

export function WorkflowView() {
  const [analytics, setAnalytics] = useState<WorkflowAnalyticsResponse | null>(
    null,
  )
  const [workflows, setWorkflows] = useState<WorkflowInstance[]>([])
  const [selectedWorkflow, setSelectedWorkflow] =
    useState<WorkflowInstance | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [detailLoading, setDetailLoading] = useState<boolean>(false)
  const [signalLoading, setSignalLoading] = useState<boolean>(false)
  const [signalType, setSignalType] = useState<WorkflowSignalType | ''>('')
  const [signalPayload, setSignalPayload] = useState<string>('')
  const [error, setError] = useState<string | null>(null)
  const [templates, setTemplates] = useState<WorkflowTemplateDefinition[]>([])
  const [editingTemplate, setEditingTemplate] =
    useState<WorkflowTemplateDefinition | null>(null)
  const [templateName, setTemplateName] = useState<string>('')
  const [templateDescription, setTemplateDescription] = useState<string>('')
  const [templateBase, setTemplateBase] = useState<WorkflowTemplate | ''>('')
  const [templateTrigger, setTemplateTrigger] = useState<string>('')
  const [templateActions, setTemplateActions] = useState<WorkflowAction[]>([])
  const [options, setOptions] = useState<WorkflowOptionsResponse | null>(null)
  const [launchCaseId, setLaunchCaseId] = useState<string>('')
  const [launchTemplate, setLaunchTemplate] = useState<WorkflowTemplate | ''>('')
  const [launching, setLaunching] = useState<boolean>(false)
  const [templateSaving, setTemplateSaving] = useState<boolean>(false)
  const [graphNodes, setGraphNodes] = useState<Array<Record<string, string>>>(
    [],
  )
  const [graphEdges, setGraphEdges] = useState<Array<Record<string, string>>>(
    [],
  )
  const [selectedNode, setSelectedNode] = useState<Record<string, string> | null>(null)

  const fetchWorkflows = useCallback(async () => {
    try {
      setError(null)
      const [analyticsResponse, workflowResponse, templateResponse, optionsResponse] =
        await Promise.all([
          getWorkflowAnalytics(),
          listWorkflows(),
          listWorkflowTemplates(),
          getWorkflowOptions(),
        ])
      setAnalytics(analyticsResponse)
      setWorkflows(workflowResponse)
      setTemplates(templateResponse)
      setOptions(optionsResponse)
      if (!templateBase && templateResponse.length > 0) {
        setTemplateBase(templateResponse[0]?.base_template ?? '')
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Unable to load workflows.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const timer = setTimeout(() => {
      void fetchWorkflows()
    }, 0)
    return () => {
      clearTimeout(timer)
    }
  }, [fetchWorkflows])

  const resetTemplateForm = () => {
    setEditingTemplate(null)
    setTemplateName('')
    setTemplateDescription('')
    setTemplateBase('')
    setTemplateTrigger('')
    setTemplateActions([])
    setGraphNodes([])
    setGraphEdges([])
    setSelectedNode(null)
  }

  const saveTemplate = async () => {
    if (!templateName.trim()) return
    try {
      setTemplateSaving(true)
      const actions = templateActions
      const nodes =
        graphNodes.length > 0
          ? graphNodes
          : actions.map((action, index) => ({
              id: `node-${index + 1}`,
              label: action,
              type: 'action',
            }))
      const edges = graphEdges
      const stoppingRules: WorkflowStoppingRules =
        editingTemplate?.stopping_rules ?? {
          max_retries: 4,
          max_touches: 5,
          max_duration_hours: 168,
          max_discount_bps: 1000,
          stop_on_recovered: true,
          stop_on_human_pause: true,
        }
      if (!templateBase || !templateTrigger.trim()) return
      if (editingTemplate) {
        await updateWorkflowTemplate({
          ...editingTemplate,
          name: templateName.trim(),
          description: templateDescription.trim(),
          base_template: templateBase,
          trigger_type: templateTrigger as WorkflowTriggerType,
          allowed_actions: actions,
          graph_nodes: nodes,
          graph_edges: edges,
          stopping_rules: stoppingRules,
        })
      } else {
        await createWorkflowTemplate({
          name: templateName.trim(),
          description: templateDescription.trim(),
          base_template: templateBase,
          trigger_type: templateTrigger as WorkflowTriggerType,
          allowed_actions: actions,
          graph_nodes: nodes,
          graph_edges: edges,
          stopping_rules: stoppingRules,
        })
      }
      resetTemplateForm()
      await fetchWorkflows()
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : 'Unable to save workflow template.',
      )
    } finally {
      setTemplateSaving(false)
    }
  }

  const editTemplate = (template: WorkflowTemplateDefinition) => {
    setEditingTemplate(template)
    setTemplateName(template.name)
    setTemplateDescription(template.description ?? '')
    setTemplateBase(template.base_template)
    setTemplateTrigger(template.trigger_type)
    setTemplateActions(template.allowed_actions)
    setGraphNodes(template.graph_nodes)
    setGraphEdges(template.graph_edges)
  }

  const removeTemplate = async (templateId: string) => {
    try {
      await deleteWorkflowTemplate(templateId)
      if (editingTemplate?.template_id === templateId) resetTemplateForm()
      await fetchWorkflows()
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : 'Unable to delete workflow template.',
      )
    }
  }

  const selectWorkflow = async (workflowId: string) => {
    try {
      setDetailLoading(true)
      setError(null)
      setSelectedWorkflow(await getWorkflow(workflowId))
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : 'Unable to load workflow details.',
      )
    } finally {
      setDetailLoading(false)
    }
  }

  const handleSignal = async () => {
    if (!selectedWorkflow || !signalType) return

    try {
      setSignalLoading(true)
      setError(null)
      let payload: Record<string, unknown> | undefined
      if (signalPayload.trim()) {
        const parsed: unknown = JSON.parse(signalPayload)
        if (
          typeof parsed !== 'object' ||
          parsed === null ||
          Array.isArray(parsed)
        ) {
          throw new Error('Signal payload must be a JSON object.')
        }
        payload = parsed as Record<string, unknown>
      }

      const updatedWorkflow = await sendWorkflowSignal(
        selectedWorkflow.workflow_id,
        {
          signal_type: signalType,
          payload,
        },
      )
      setSelectedWorkflow(updatedWorkflow)
      setSignalType('')
      setSignalPayload('')
      await fetchWorkflows()
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : 'Unable to deliver workflow signal.',
      )
    } finally {
      setSignalLoading(false)
    }
  }

  const handleLaunch = async () => {
    if (!launchCaseId.trim()) return
    try {
      setLaunching(true)
      setError(null)
      await launchWorkflow(launchCaseId.trim(), launchTemplate || undefined)
      setLaunchCaseId('')
      await fetchWorkflows()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Unable to launch workflow.')
    } finally {
      setLaunching(false)
    }
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonRow />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 border-b border-border pb-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <GitBranch className="h-5 w-5 text-accent" />
            <h1 className="font-mono text-2xl font-bold text-ink">
              FORTX Workflows
            </h1>
          </div>
          <p className="mt-0.5 text-sm text-ink-muted">
            Durable recovery workflows, decision history, and event-driven
            controls.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            setLoading(true)
            void fetchWorkflows()
          }}
          disabled={loading}
          className="font-mono"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Refresh
        </Button>
      </div>

      {error && (
        <div className="rounded-panel border border-failed/30 bg-failed-subtle px-4 py-3 text-sm text-failed">
          {error}
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        <StatCard
          title="Total Workflows"
          value={analytics ? analytics.total_workflows.toString() : '-'}
          subtitle="Persisted workflow instances"
          icon={<GitBranch className="h-4 w-4 text-accent" />}
          variant="accent"
        />
        <StatCard
          title="Active Stages"
          value={
            analytics
              ? Object.keys(analytics.stage_counts).length.toString()
              : '-'
          }
          subtitle="Stages currently represented"
          icon={<Activity className="h-4 w-4 text-pending" />}
        />
        <StatCard
          title="Workflow Templates"
          value={
            analytics
              ? Object.keys(analytics.template_counts).length.toString()
              : '-'
          }
          subtitle="Recovery paths currently represented"
          icon={<Clock3 className="h-4 w-4 text-ink-muted" />}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader className="p-5 pb-3">
            <CardTitle className="font-mono text-base">
              Stage Breakdown
            </CardTitle>
            <CardDescription>
              Live stage counts from the workflow engine.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 p-5 pt-0">
            {Object.entries(analytics?.stage_counts ?? {}).map(
              ([stage, count]) => (
                <div
                  key={stage}
                  className="flex items-center justify-between rounded-control border border-border px-3 py-2"
                >
                  <Badge variant={badgeForStage(stage)}>
                    {labelFor(stage)}
                  </Badge>
                  <span className="font-mono text-sm font-bold text-ink">
                    {count.toString()}
                  </span>
                </div>
              ),
            )}
            {Object.keys(analytics?.stage_counts ?? {}).length === 0 && (
              <p className="text-sm text-ink-muted">
                No workflow stages are available.
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="p-5 pb-3">
            <CardTitle className="font-mono text-base">
              Template Breakdown
            </CardTitle>
            <CardDescription>
              Built-in lifecycle templates in persisted use.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 p-5 pt-0">
            {Object.entries(analytics?.template_counts ?? {}).map(
              ([template, count]) => (
                <div
                  key={template}
                  className="flex items-center justify-between rounded-control border border-border px-3 py-2"
                >
                  <span className="font-mono text-xs font-semibold text-ink">
                    {labelFor(template)}
                  </span>
                  <span className="font-mono text-sm font-bold text-ink">
                    {count.toString()}
                  </span>
                </div>
              ),
            )}
            {Object.keys(analytics?.template_counts ?? {}).length === 0 && (
              <p className="text-sm text-ink-muted">
                No workflow templates are available.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="p-5 pb-3">
          <CardTitle className="font-mono text-base">
            Template Authoring
          </CardTitle>
          <CardDescription>
            Create and manage persisted workflow definitions anchored to
            built-in lifecycles.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 p-5 pt-0">
          <div className="grid gap-2 md:grid-cols-4">
            <input
              value={templateName}
              onChange={(event) => {
                setTemplateName(event.target.value)
              }}
              placeholder="Template name"
              className="h-8 rounded-control border border-border bg-surface px-2 font-mono text-xs"
            />
            <input value={templateDescription} onChange={(event) => setTemplateDescription(event.target.value)} placeholder="What this workflow recovers" className="h-8 rounded-control border border-border bg-surface px-2 font-mono text-xs" />
            <select
              value={templateBase}
              onChange={(event) => {
                setTemplateBase(event.target.value as WorkflowTemplate | '')
              }}
              className="h-8 rounded-control border border-border bg-surface px-2 font-mono text-xs"
            >
              {Array.from(
                new Set(templates.map((template) => template.base_template)),
              ).map((value) => (
                <option key={value} value={value}>
                  {labelFor(value)}
                </option>
              ))}
            </select>
            <select
              value={templateTrigger}
              onChange={(event) => setTemplateTrigger(event.target.value)}
              className="h-8 rounded-control border border-border bg-surface px-2 font-mono text-xs"
            >
              <option value="">Select trigger</option>
              {(options?.trigger_types ?? []).map((value) => (
                <option key={value} value={value}>{value}</option>
              ))}
            </select>
            <div className="flex flex-wrap items-center gap-2 rounded-control border border-border bg-surface px-2 py-1">
              {(options?.actions ?? []).map((action) => (
                <label key={action} className="flex items-center gap-1 font-mono text-[10px] text-ink-muted">
                  <input
                    type="checkbox"
                    checked={templateActions.includes(action)}
                    onChange={() => setTemplateActions((current) => current.includes(action) ? current.filter((item) => item !== action) : [...current, action])}
                  />
                  {action}
                </label>
              ))}
            </div>
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              onClick={() => {
                void saveTemplate()
              }}
              disabled={
                templateSaving ||
                !templateName.trim() ||
                !templateBase ||
                !templateTrigger.trim()
              }
              className="font-mono"
            >
              {editingTemplate ? 'Update Template' : 'Create Template'}
            </Button>
            {editingTemplate && (
              <Button
                size="sm"
                variant="ghost"
                onClick={resetTemplateForm}
                className="font-mono"
              >
                Cancel
              </Button>
            )}
          </div>
          <div className="rounded-panel border border-border bg-surface-sunken p-4">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <p className="font-mono text-xs font-bold text-ink">
                  Workflow graph
                </p>
                <p className="text-[11px] text-ink-muted">
                  Nodes execute left to right through the bounded backend
                  lifecycle.
                </p>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setGraphNodes((nodes) => [
                    ...nodes,
                    {
                      id: `node-${nodes.length + 1}`,
                      label: `Step ${nodes.length + 1}`,
                      type: 'action',
                    },
                  ])
                }}
              >
                <Plus className="h-3.5 w-3.5" />
                Add node
              </Button>
            </div>
            <GraphEditor
              key={`graph-${graphNodes.length.toString()}-${graphEdges.length.toString()}`}
              nodes={graphNodes}
              edges={graphEdges}
              onChange={(nodes, edges) => {
                setGraphNodes(nodes)
                setGraphEdges(edges)
              }}
              onSelectNode={setSelectedNode}
            />
            {graphNodes.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-2">
                {graphNodes.map((node) => (
                  <button key={node.id} type="button" onClick={() => setSelectedNode(node)} className="flex items-center gap-1 rounded-control border border-accent/30 bg-surface px-2 py-1 font-mono text-[10px] text-ink">
                    {iconForNodeType(node.type ?? 'action')}{node.label ?? node.id}
                  </button>
                ))}
              </div>
            )}
            {selectedNode && (
              <div className="mt-3 flex items-center gap-2 rounded-control border border-border bg-surface px-3 py-2">
                <span className="font-mono text-[10px] uppercase text-ink-muted">Edit node</span>
                <input value={selectedNode.label ?? ''} onChange={(event) => {
                  const label = event.target.value
                  setSelectedNode({ ...selectedNode, label })
                  setGraphNodes((current) => current.map((node) => node.id === selectedNode.id ? { ...node, label } : node))
                }} className="h-7 flex-1 rounded-control border border-border bg-surface px-2 font-mono text-xs" />
                <span className="rounded-control bg-surface-sunken px-2 py-1 font-mono text-[10px] text-accent">{selectedNode.type}</span>
              </div>
            )}
          </div>
          <div className="space-y-2">
            {templates.map((template) => (
              <div
                key={template.template_id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-control border border-border px-3 py-2"
              >
                <div>
                  <p className="font-mono text-xs font-bold text-ink">
                    {template.name}
                  </p>
                  <p className="font-mono text-[10px] text-ink-muted">
                    {labelFor(template.base_template)} | {template.trigger_type}
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      editTemplate(template)
                    }}
                  >
                    <GitBranch className="h-3.5 w-3.5" />
                    Edit
                  </Button>
                  <Button
                    size="sm"
                    variant="danger"
                    onClick={() => {
                      void removeTemplate(template.template_id)
                    }}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    Delete
                  </Button>
                </div>
              </div>
            ))}
            {templates.length === 0 && (
              <p className="text-sm text-ink-muted">
                No authored templates yet.
              </p>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="p-5 pb-3">
          <CardTitle className="font-mono text-base">Launch workflow</CardTitle>
          <CardDescription>Attach a durable workflow to an existing recovery case.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 p-5 pt-0 sm:flex-row">
          <input value={launchCaseId} onChange={(event) => setLaunchCaseId(event.target.value)} placeholder="Recovery case ID" className="h-8 flex-1 rounded-control border border-border bg-surface px-2 font-mono text-xs" />
          <select value={launchTemplate} onChange={(event) => setLaunchTemplate(event.target.value as WorkflowTemplate | '')} className="h-8 rounded-control border border-border bg-surface px-2 font-mono text-xs">
            <option value="">Default template</option>
            {(options?.trigger_types ?? []).map((trigger) => {
              const match = templates.find((item) => item.trigger_type === trigger)
              return match ? <option key={match.base_template} value={match.base_template}>{match.name}</option> : null
            })}
          </select>
          <Button size="sm" onClick={() => void handleLaunch()} disabled={launching || !launchCaseId.trim()} className="font-mono"><GitBranch className="h-3.5 w-3.5" />{launching ? 'Launching...' : 'Launch'}</Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="p-5 pb-3">
          <CardTitle className="font-mono text-base">
            Workflow Registry
          </CardTitle>
          <CardDescription>
            Select a workflow to inspect its replayable history and deliver an
            external signal.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Workflow</TableHead>
                <TableHead>Case</TableHead>
                <TableHead>Template</TableHead>
                <TableHead>Stage</TableHead>
                <TableHead className="text-right">Attempts</TableHead>
                <TableHead>Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {workflows.map((workflow) => (
                <TableRow
                  key={workflow.workflow_id}
                  className="cursor-pointer hover:bg-surface-sunken/60"
                  onClick={() => {
                    void selectWorkflow(workflow.workflow_id)
                  }}
                >
                  <TableCell className="font-mono text-xs font-semibold text-ink">
                    {workflow.workflow_id}
                  </TableCell>
                  <TableCell className="font-mono text-xs text-ink-muted">
                    {workflow.case_id}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {labelFor(workflow.template)}
                  </TableCell>
                  <TableCell>
                    <Badge variant={badgeForStage(workflow.current_stage)}>
                      {labelFor(workflow.current_stage)}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs">
                    {workflow.attempts_count.toString()}
                  </TableCell>
                  <TableCell className="font-mono text-xs text-ink-muted">
                    {formatTimestamp(workflow.updated_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {workflows.length === 0 && (
            <p className="p-5 text-sm text-ink-muted">
              No persisted workflows are available.
            </p>
          )}
        </CardContent>
      </Card>

      {(detailLoading || selectedWorkflow) && (
        <Card className="border-accent/30">
          <CardHeader className="p-5 pb-3">
            <CardTitle className="font-mono text-base">
              Workflow Detail
            </CardTitle>
            <CardDescription>
              {selectedWorkflow
                ? `${selectedWorkflow.workflow_id} for case ${selectedWorkflow.case_id}`
                : 'Loading workflow detail...'}
            </CardDescription>
          </CardHeader>
          {detailLoading && (
            <CardContent className="p-5 pt-0">
              <SkeletonRow />
            </CardContent>
          )}
          {selectedWorkflow && !detailLoading && (
            <CardContent className="space-y-6 p-5 pt-0">
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <div className="rounded-control border border-border bg-surface-sunken p-3">
                  <p className="font-mono text-[11px] text-ink-muted">
                    Current stage
                  </p>
                  <Badge
                    variant={badgeForStage(selectedWorkflow.current_stage)}
                  >
                    {labelFor(selectedWorkflow.current_stage)}
                  </Badge>
                </div>
                <div className="rounded-control border border-border bg-surface-sunken p-3">
                  <p className="font-mono text-[11px] text-ink-muted">
                    Recovery state
                  </p>
                  <p className="mt-1 font-mono text-xs font-semibold text-ink">
                    {labelFor(selectedWorkflow.recovery_state)}
                  </p>
                </div>
                <div className="rounded-control border border-border bg-surface-sunken p-3">
                  <p className="font-mono text-[11px] text-ink-muted">
                    Touches
                  </p>
                  <p className="mt-1 font-mono text-lg font-bold text-ink">
                    {selectedWorkflow.touches_count.toString()}
                  </p>
                </div>
                <div className="rounded-control border border-border bg-surface-sunken p-3">
                  <p className="font-mono text-[11px] text-ink-muted">
                    Terminal outcome
                  </p>
                  <p className="mt-1 font-mono text-xs font-semibold text-ink">
                    {selectedWorkflow.terminal_outcome ?? 'Active'}
                  </p>
                </div>
              </div>

              <div className="grid gap-6 xl:grid-cols-2">
                <div>
                  <h3 className="mb-3 font-mono text-sm font-bold text-ink">
                    Execution History
                  </h3>
                  <div className="max-h-96 space-y-2 overflow-y-auto pr-1">
                    {selectedWorkflow.history.map((event) => (
                      <div
                        key={event.event_id}
                        className="rounded-control border border-border p-3"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="font-mono text-xs font-bold text-ink">
                            {labelFor(event.event_name)}
                          </span>
                          <span className="font-mono text-[10px] text-ink-muted">
                            {formatTimestamp(event.timestamp)}
                          </span>
                        </div>
                        <p className="mt-1 font-mono text-[11px] text-ink-muted">
                          {event.from_stage
                            ? `${labelFor(event.from_stage)} -> `
                            : ''}
                          {labelFor(event.to_stage)}
                        </p>
                        {Object.keys(event.details).length > 0 && (
                          <pre className="mt-2 overflow-x-auto rounded-control bg-surface-sunken p-2 font-mono text-[10px] text-ink-muted">
                            {formatDetails(event.details)}
                          </pre>
                        )}
                      </div>
                    ))}
                    {selectedWorkflow.history.length === 0 && (
                      <p className="text-sm text-ink-muted">
                        No execution events are available.
                      </p>
                    )}
                  </div>
                </div>

                <div className="space-y-6">
                  <div>
                    <h3 className="mb-3 font-mono text-sm font-bold text-ink">
                      Received Signals
                    </h3>
                    <div className="max-h-48 space-y-2 overflow-y-auto pr-1">
                      {selectedWorkflow.signals_received.map((signal) => (
                        <div
                          key={signal.signal_id}
                          className="rounded-control border border-border p-3"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-mono text-xs font-bold text-ink">
                              {labelFor(signal.signal_type)}
                            </span>
                            <span className="font-mono text-[10px] text-ink-muted">
                              {formatTimestamp(signal.timestamp)}
                            </span>
                          </div>
                          <p className="mt-1 font-mono text-[10px] text-ink-muted">
                            Source: {signal.source}
                          </p>
                        </div>
                      ))}
                      {selectedWorkflow.signals_received.length === 0 && (
                        <p className="text-sm text-ink-muted">
                          No signals have been recorded.
                        </p>
                      )}
                    </div>
                  </div>

                  <div className="rounded-panel border border-accent/30 bg-accent/5 p-4">
                    <h3 className="font-mono text-sm font-bold text-ink">
                      Deliver Signal
                    </h3>
                    <p className="mt-1 text-xs text-ink-muted">
                      Submit a backend-validated workflow event. Payload is
                      optional JSON.
                    </p>
                    <input
                      type="text"
                      value={signalType}
                      onChange={(event) => {
                        setSignalType(
                          event.target.value as WorkflowSignalType | '',
                        )
                      }}
                      placeholder="Signal type"
                      className="mt-3 h-8 w-full rounded-control border border-border bg-surface px-2.5 font-mono text-xs text-ink outline-none focus:border-accent"
                    />
                    <textarea
                      value={signalPayload}
                      onChange={(event) => {
                        setSignalPayload(event.target.value)
                      }}
                      placeholder="Optional JSON payload"
                      rows={3}
                      className="mt-2 w-full rounded-control border border-border bg-surface p-2.5 font-mono text-xs text-ink outline-none focus:border-accent"
                    />
                    <Button
                      size="sm"
                      onClick={() => {
                        void handleSignal()
                      }}
                      disabled={signalLoading || !signalType}
                      className="mt-3 font-mono"
                    >
                      <Send className="h-3.5 w-3.5" />
                      {signalLoading ? 'Delivering' : 'Deliver Signal'}
                    </Button>
                  </div>
                </div>
              </div>
            </CardContent>
          )}
        </Card>
      )}
    </div>
  )
}
