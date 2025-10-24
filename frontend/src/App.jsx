import "./App.css";
import React, { useEffect, useState } from "react";
import axios from "axios";

export default function App() {
  const [people, setPeople] = useState([]);
  const [editId, setEditId] = useState(null);
  const [replication, setReplication] = useState({});
  const [name, setName] = useState("");
  const [age, setAge] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [history, setHistory] = useState([]);
  const [showHistoryId, setShowHistoryId] = useState(null);
  const [isNodeDown, setIsNodeDown] = useState(false);

  const [selectedNode, setSelectedNode] = useState("node_A");
  const [role, setRole] = useState("Primary");

  const API = {
    node_A: "http://127.0.0.1:5000",
    node_B: "http://127.0.0.1:5001",
    node_C: "http://127.0.0.1:5002",
  };

  // ==== LOAD DỮ LIỆU THEO NODE ====
  const loadPeople = async () => {
    try {
      const res = await axios.get(`${API[selectedNode]}/people`);
      setPeople(res.data.data || []);
      setRole(res.data.role || "Replica");
    } catch (err) {
      console.error("Lỗi khi gọi API:", err);
      setPeople([]);
    }
  };

  const loadReplicationStatus = async () => {
    try {
      const res = await axios.get(`${API.node_A}/replication-status`);
      setReplication(res.data);
    } catch (err) {
      console.error("Lỗi lấy replication:", err);
    }
  };

  // ==== Auto refresh mỗi 3 giây ====
  useEffect(() => {
    loadPeople();
    loadReplicationStatus();
    const interval = setInterval(() => {
      loadReplicationStatus();
      loadPeople();
    }, 3000);
    return () => clearInterval(interval);
  }, [selectedNode]);

  // ==== Undo / Redo / CRUD ====
  const undoPerson = async (id) => {
    try {
      const res = await axios.post(`${API[selectedNode]}/people/${id}/undo`);
      loadPeople();
      setHistory(res.data.history);
      setShowHistoryId(id);
    } catch (err) {
      alert("Không thể undo: " + err.response.data.error);
    }
  };

  const redoPerson = async (id) => {
    try {
      const res = await axios.post(`${API[selectedNode]}/people/${id}/redo`);
      loadPeople();
      setHistory(res.data.history);
      setShowHistoryId(id);
    } catch (err) {
      alert("Không thể redo: " + err.response.data.error);
    }
  };

  const viewHistory = async (id) => {
    try {
      const res = await axios.get(`${API[selectedNode]}/people/${id}/history`);
      setHistory(res.data);
      setShowHistoryId(id);
    } catch {
      alert("Không có lịch sử cho " + id);
    }
  };

  const deletePerson = async (id) => {
    await axios.delete(`${API[selectedNode]}/people/${id}`);
    loadPeople();
  };

  const startEdit = (p) => {
    setEditId(p.id);
    setName(p.name);
    setAge(p.age);
    setShowForm(true);
  };

  const addPerson = async () => {
    if (!name || !age) return alert("Nhập đủ thông tin");
    await axios.post(`${API[selectedNode]}/people`, {
      name,
      age: parseInt(age),
    });
    setName("");
    setAge("");
    setShowForm(false);
    loadPeople();
  };

  const updatePerson = async () => {
    if (!editId) return;
    await axios.put(`${API[selectedNode]}/people/${editId}`, {
      name,
      age: parseInt(age),
    });
    setEditId(null);
    setName("");
    setAge("");
    setShowForm(false);
    loadPeople();
  };

  const openAddForm = () => {
    setEditId(null);
    setName("");
    setAge("");
    setShowForm(true);
  };

  const closeForm = () => {
    setEditId(null);
    setName("");
    setAge("");
    setShowForm(false);
  };

  // ==== Phân tán ====
  const runReplication = async () => {
    try {
      const res = await axios.post(`${API[selectedNode]}/run-replication`, {
        nodes: ["node_A", "node_B", "node_C"],
      });
      console.log("Replication:", res.data);
      loadReplicationStatus();
      alert("Replication đã khởi chạy!");
    } catch {
      alert("Lỗi replication");
    }
  };

  const disconnectNode = async () => {
    await axios.post(`${API.node_A}/simulate-failure`);
    setIsNodeDown(true);
    alert("Node chính đã bị ngắt kết nối!");
  };

  const reconnectNode = async () => {
    await axios.post(`${API.node_A}/restore-primary`);
    setIsNodeDown(false);
    alert("Node chính đã được khôi phục!");
  };

  return (
    <div className="app-container">
      <nav className="navigator">
        <h2> Hệ thống ZODB Replication</h2>
        <div className="node-selector">
          <label> Xem dữ liệu tại node:</label>
          <select
            value={selectedNode}
            onChange={(e) => setSelectedNode(e.target.value)}
          >
            <option value="node_A">Node A</option>
            <option value="node_B">Node B</option>
            <option value="node_C">Node C</option>
          </select>
          <span
            className={`node-role ${
              role === "Primary" ? "primary" : "replica"
            }`}
          >
            {role === "Primary" ? " Primary" : " Replica"}
          </span>
        </div>
      </nav>

      <div className="content">
        <h2>Danh sách nhân viên ({selectedNode})</h2>

        <div className="replication-status">
          <h4>Replication Status</h4>
          {Object.entries(replication).map(([node, status]) => (
            <div key={node} className={`status-item ${status}`}>
              <span className="node-name">{node}</span>
              <span className="status-icon">
                {status === "synced"
                  ? "✔️"
                  : status === "pending"
                  ? "⏳"
                  : "❌"}
              </span>
              <span className="status-text">
                {status === "synced"
                  ? "Đã đồng bộ"
                  : status === "pending"
                  ? "Đang đồng bộ"
                  : "Lỗi"}
              </span>
            </div>
          ))}

          <div className="replication-buttons">
            <button onClick={runReplication} className="btn-replicate">
              Chạy Replication
            </button>
            <button
              onClick={disconnectNode}
              className="btn-fail"
              disabled={isNodeDown}
            >
              Mất kết nối node chính
            </button>
            <button
              onClick={reconnectNode}
              className="btn-recover"
              disabled={!isNodeDown}
            >
              Khôi phục node chính
            </button>
          </div>
        </div>

        <button className="btn-add" onClick={openAddForm}>
          Thêm nhân viên
        </button>

        {people.length === 0 ? (
          <p className="database"> Chưa có dữ liệu trong node {selectedNode}</p>
        ) : (
          <table className="people-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Tên</th>
                <th>Tuổi</th>
                <th>Hành động</th>
              </tr>
            </thead>
            <tbody>
              {people.map((p) => (
                <tr
                  key={p.id}
                  className={`tr ${p.is_deleted ? "deleted-row" : ""}`}
                  style={{ opacity: p.is_deleted ? 0.5 : 1 }}
                >
                  <td>{p.id}</td>
                  <td>{p.name}</td>
                  <td>{p.age}</td>
                  <td>
                    {!p.is_deleted ? (
                      <>
                        <button
                          onClick={() => deletePerson(p.id)}
                          className="btn-delete"
                        >
                          Xóa
                        </button>
                        <button
                          onClick={() => startEdit(p)}
                          className="btn-edit"
                        >
                          Sửa
                        </button>
                        <button
                          onClick={() => undoPerson(p.id)}
                          className="btn-undo"
                        >
                          Undo
                        </button>
                        <button
                          onClick={() => redoPerson(p.id)}
                          className="btn-redo"
                        >
                          Redo
                        </button>
                        <button
                          onClick={() => viewHistory(p.id)}
                          className="btn-history"
                        >
                          Lịch sử
                        </button>
                      </>
                    ) : (
                      <>
                        <span className="deleted-text">Đã xóa</span>
                        <button
                          onClick={() => undoPerson(p.id)}
                          className="btn-undo"
                        >
                          Khôi phục
                        </button>
                        <button
                          onClick={() => viewHistory(p.id)}
                          className="btn-history"
                        >
                          Lịch sử
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {/* FORM */}
        {showForm && (
          <div className="modal-overlay">
            <div className="modal">
              <h2>{editId ? "Cập nhật nhân viên" : "Thêm nhân viên"}</h2>
              <input
                placeholder="Tên"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <input
                placeholder="Tuổi"
                type="number"
                value={age}
                onChange={(e) => setAge(e.target.value)}
              />
              <div className="modal-actions">
                {editId ? (
                  <button onClick={updatePerson} className="btn-save">
                    Cập nhật
                  </button>
                ) : (
                  <button onClick={addPerson} className="btn-save">
                    Thêm
                  </button>
                )}
                <button onClick={closeForm} className="btn-cancel">
                  Hủy
                </button>
              </div>
            </div>
          </div>
        )}

        {/* LỊCH SỬ */}
        {showHistoryId && (
          <div className="modal-overlay">
            <div className="modal">
              <h3>Lịch sử phiên bản của {showHistoryId}</h3>
              <ul>
                {history.map((h, i) => (
                  <li key={i} className="history">
                    {i + 1}. {h.name} - {h.age}
                  </li>
                ))}
              </ul>
              <button
                onClick={() => setShowHistoryId(null)}
                className="btn-cancel"
              >
                Đóng
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
