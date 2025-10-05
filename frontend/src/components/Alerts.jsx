import {
  CTable,
  CTableHead,
  CTableRow,
  CTableHeaderCell,
  CTableBody,
  CTableDataCell,
} from "@coreui/react";

    // TODO: replace with API call once backend is ready

function Alerts() {
  return (
    <div className="p-4">
      <h2>Alers Table</h2>
      <CTable color="dark" striped>
        <CTableHead>
          <CTableRow>
            <CTableHeaderCell scope="col">Time</CTableHeaderCell>
            <CTableHeaderCell scope="col">Truck ID</CTableHeaderCell>
            <CTableHeaderCell scope="col">Alert Type</CTableHeaderCell>
            <CTableHeaderCell scope="col">Description</CTableHeaderCell>
          </CTableRow>
        </CTableHead>
        <CTableBody>
          <CTableRow>
            <CTableHeaderCell scope="row">10:15 AM</CTableHeaderCell>
            <CTableDataCell>TRK - 101</CTableDataCell>
            <CTableDataCell>Fuel</CTableDataCell>
            <CTableDataCell>Anomalous Fuel Usage</CTableDataCell>
          </CTableRow>
          <CTableRow>
            <CTableHeaderCell scope="row">11:30 AM</CTableHeaderCell>
            <CTableDataCell>TRK - 202</CTableDataCell>
            <CTableDataCell>Maintenance</CTableDataCell>
            <CTableDataCell>Maintenance Check</CTableDataCell>
          </CTableRow>
          <CTableRow>
            <CTableHeaderCell scope="row">01:00 AM</CTableHeaderCell>
            <CTableDataCell>TRK - 303</CTableDataCell>
            <CTableDataCell>Rest</CTableDataCell>
            <CTableDataCell>Have been driving for too long</CTableDataCell>
          </CTableRow>
        </CTableBody>
      </CTable>
    </div>
  );
}


export default Alerts;
