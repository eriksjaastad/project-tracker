import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Navigation } from './components/Navigation';
import { KanbanBoard } from './components/KanbanBoard';
import './App.css';

function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <Navigation />
        <main className="app-main">
          <Routes>
            <Route path="/" element={<Navigate to="/kanban" replace />} />
            <Route path="/kanban" element={<KanbanBoard />} />
            <Route path="/kanban/:project" element={<KanbanBoard />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
