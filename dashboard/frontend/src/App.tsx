import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Navigation } from './components/Navigation';
import { DashboardPage } from './components/DashboardPage';
import { KanbanBoard } from './components/KanbanBoard';
import { AgenticDashboard } from './components/AgenticDashboard';
import { CalendarPage } from './components/CalendarPage';
import { AgentChatPage } from './components/AgentChatPage';
import { JobsPage } from './components/JobsPage';
import { JobsSubmittedPage } from './components/JobsSubmittedPage';
import { CodebasePage } from './components/CodebasePage';
import { MorningPage } from './components/MorningPage';
import './App.css';

function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <Navigation />
        <Routes>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/kanban" element={<KanbanBoard />} />
          <Route path="/kanban/:project" element={<KanbanBoard />} />
          <Route path="/agentic" element={<AgenticDashboard />} />
          <Route path="/calendar" element={<CalendarPage />} />
          <Route path="/agent-chat" element={<AgentChatPage />} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/jobs/submitted" element={<JobsSubmittedPage />} />
          <Route path="/codebase" element={<CodebasePage />} />
          <Route path="/morning" element={<MorningPage />} />
          <Route path="*" element={<Navigate to="/kanban" replace />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;
