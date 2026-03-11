import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Navigation } from './components/Navigation';
import { KanbanBoard } from './components/KanbanBoard';
import { AgenticDashboard } from './components/AgenticDashboard';
import './App.css';

function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <Navigation />
        <Routes>
          <Route path="/kanban" element={<KanbanBoard />} />
          <Route path="/kanban/:project" element={<KanbanBoard />} />
          <Route path="/agentic" element={<AgenticDashboard />} />
          <Route path="*" element={<Navigate to="/kanban" replace />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;
